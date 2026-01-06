# =====================================
# inference_engine.py — Local Mistral-7B Inference Core
# Optimized for RTX 3090/4090 | 4-bit quantized
# Simplified for public framework — no DB, no heartbeat
# =====================================
import os
import json
import time
import torch
import gc
import portalocker
import logging
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

# =====================================
# CONFIG
# =====================================
MESSAGE_PATH = "message.json"
MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"
PRECISION_MODE = "4bit"                 # "4bit", "8bit", "fp16"
MAX_NEW_TOKENS = 1024

# Logging (quiet by default)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# =====================================
# VRAM Safety (80% clamp)
# =====================================
if torch.cuda.is_available():
    total_vram = torch.cuda.get_device_properties(0).total_memory
    total_gb = total_vram / (1024 ** 3)
    clamp_gb = max(round(total_gb * 0.80, 2), 3.0)
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "garbage_collection_threshold:0.8,max_split_size_mb:256"
    logging.info(f"VRAM clamped to {clamp_gb:.2f} GiB ({total_gb:.2f} GiB total)")
else:
    logging.warning("CUDA not available — running on CPU")

# =====================================
# Quantization Config
# =====================================
bnb_config = None
torch_dtype = torch.float16

if PRECISION_MODE == "4bit":
    logging.info("Loading in 4-bit (float16 compute)")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
elif PRECISION_MODE == "8bit":
    bnb_config = BitsAndBytesConfig(load_in_8bit=True)
elif PRECISION_MODE == "fp16":
    pass
else:
    raise ValueError("Invalid PRECISION_MODE")

# =====================================
# Load Model & Tokenizer
# =====================================
logging.info(f"Loading {MODEL_NAME}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "left"

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    device_map="auto",
    torch_dtype=torch_dtype,
    quantization_config=bnb_config,
    low_cpu_mem_usage=True,
)
model.eval()
model.config.use_cache = True
logging.info("Model loaded.")

# =====================================
# Memory Cleanup
# =====================================
def clear_vram():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# =====================================
# Inference
# =====================================
def run_inference(prompt: str) -> str:
    try:
        messages = [{"role": "user", "content": prompt}]
        chat_text = tokenizer.apply_chat_template(messages, tokenize=False)
        inputs = tokenizer(chat_text, return_tensors="pt").to(model.device)

        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                temperature=0.74,
                top_p=0.9,
                top_k=40,
                do_sample=True,
                repetition_penalty=1.25,
                pad_token_id=tokenizer.eos_token_id,
            )
        response = tokenizer.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        return response.strip()
    except torch.cuda.OutOfMemoryError:
        clear_vram()
        return "Warning: Out of memory — response truncated."
    except Exception as e:
        logging.error(f"Inference error: {e}")
        return "Error during generation."
    finally:
        clear_vram()

# =====================================
# Message Loop (file-based IPC)
# =====================================
logging.info("Engine ready — watching message.json for prompts...")

while True:
    if not os.path.exists(MESSAGE_PATH):
        time.sleep(1)
        continue
    try:
        with open(MESSAGE_PATH, "r+", encoding="utf-8") as f:
            portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
            data = json.load(f)

            if data.get("type") == "prompt" and data.get("content"):
                logging.info("Prompt received")
                prompt = data["content"]

                # Build the full rich prompt with identity, history, etc.
                from prompt_builder import build_full_prompt
                rich_prompt = build_full_prompt(prompt)

                # Single inference using the complete prompt
                response = run_inference(rich_prompt)

                # Write reply back
                f.seek(0)
                f.truncate()
                json.dump({"type": "reply", "content": response}, f, indent=2)
                f.flush()
                logging.info("Reply sent")

            portalocker.unlock(f)

    except portalocker.exceptions.LockException:
        time.sleep(0.5)
    except Exception as e:
        logging.error(f"IPC error: {e}")
        time.sleep(1)
