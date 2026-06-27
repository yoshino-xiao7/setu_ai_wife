# OPERATIONS

## Health checklist

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_env.ps1
```

Then check:

- `http://127.0.0.1:8188` opens ComfyUI.
- `http://127.0.0.1:7861` opens the local service.

## Common failures

### Python opens Microsoft Store

Install Python 3.12 with `winget install --id Python.Python.3.12 -e`, then reopen PowerShell.

### ComfyUI says checkpoint not found

Set `DEFAULT_CHECKPOINT` in `.env` to the exact filename in `ComfyUI\models\checkpoints`.

### Ollama is unavailable

The service falls back to a template prompt. To restore translation:

```powershell
ollama pull qwen3:4b
ollama list
```

### CUDA out of memory

Use a smaller image size, fewer steps, or a lighter checkpoint. Start with `768x1024`, then reduce to `768x768` if needed.

### Service cannot connect to ComfyUI

Start ComfyUI first and confirm it is reachable at `http://127.0.0.1:8188`.

## Backups

Back up:

- `data/jobs.sqlite3`
- `outputs/`
- `.env`

ComfyUI model files are large; back them up separately if needed.

