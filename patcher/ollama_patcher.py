import httpx
from database import get_session, Patch
from config import OLLAMA_HOST

OLLAMA_MODEL = "codellama:7b"
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"

def build_prompt(original_code: str, changelog_content: str, file_path: str) -> str:
    return f"""You are a Python code migration expert specializing in Stripe API upgrades.

A Stripe API change has been detected. Here is what changed:
---CHANGELOG---
{changelog_content[1000:3500]}
---END CHANGELOG---

Here is the Python file that needs to be updated ({file_path}):
---ORIGINAL CODE---
{original_code}
---END CODE---

Rewrite the code to be compatible with the latest Stripe API version.
Rules you must follow:
- Only change what is necessary to fix the Stripe API compatibility
- Keep all logic, comments, and structure identical
- Return ONLY the complete updated Python code
- No explanations, no markdown, no triple backticks
- The output must be valid runnable Python

Updated code:"""

def clean_code_output(raw: str) -> str:
    lines = raw.strip().split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    clean = "\n".join(lines).strip()
    last_import = -1
    for i, line in enumerate(clean.split("\n")):
        stripped = line.strip()
        if (stripped.startswith("import ")
                or stripped.startswith("from ")
                or stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("if ")
                or stripped.startswith("@")
                or stripped.startswith("#")
                or stripped == ""):
            last_code_line = i
    code_lines = clean.split("\n")
    for i in range(len(code_lines) - 1, -1, -1):
        line = code_lines[i].strip()
        if line == "" or line.startswith("#"):
            continue
        if not any([
            line.endswith(":"),
            line.endswith(","),
            line.endswith(")"),
            line.endswith("]"),
            line.endswith("}"),
            line.endswith("'"),
            line.endswith('"'),
            line.startswith("return "),
            line.startswith("import "),
            line.startswith("from "),
        ]):
            if len(line.split()) > 6 and not line.startswith(("def ", "class ", "if ", "elif ", "else", "for ", "while ", "with ", "try", "except")):
                code_lines = code_lines[:i]
        break
    return "\n".join(code_lines).strip()

async def call_ollama(prompt: str) -> str:   # ← column 0, no indentation
    print(f"[Patcher] Sending prompt to Ollama ({OLLAMA_MODEL})...")
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 2048,
                    "num_ctx": 8192,
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        return clean_code_output(data["response"])

def save_patched_code(patch_id: int, patched_code: str) -> Patch:
    session = get_session()
    try:
        patch = session.query(Patch).filter_by(id=patch_id).first()
        if not patch:
            raise ValueError(f"Patch id={patch_id} not found in database")
        patch.patched_code = patched_code
        patch.status = "patched"
        session.commit()
        session.refresh(patch)
        return patch
    finally:
        session.close()

async def generate_patch(patch: Patch, changelog_content: str) -> Patch | None:
    print(f"[Patcher] Processing {patch.file_path}")
    try:
        prompt = build_prompt(patch.original_code, changelog_content, patch.file_path)
        patched_code = await call_ollama(prompt)
        updated_patch = save_patched_code(patch.id, patched_code)
        print(f"[Patcher] Fix saved for patch id={patch.id}")
        return updated_patch
    except Exception as e:
        print(f"[Patcher] Failed on patch id={patch.id}: {type(e).__name__}: {e}")
        return None


async def run_patcher(patches: list, changelog_content: str) -> list:
    print(f"[Patcher] Starting. {len(patches)} file(s) to patch.")
    results = []
    for patch in patches:
        result = await generate_patch(patch, changelog_content)
        if result:
            results.append(result)
    print(f"[Patcher] Done. {len(results)}/{len(patches)} file(s) patched.")
    return results