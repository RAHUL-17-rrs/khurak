# =============================================================================================
# Host Gnani Evon v3.3 (30B-A3B, Apache-2.0) for Khurak on a FREE Kaggle GPU notebook.
#
# Kaggle -> New Notebook -> Settings: Accelerator = "GPU T4 x2", Internet = ON.
# Paste each CELL into its own notebook cell and run top to bottom (~15 min the first time).
# The last cell prints a public https URL. Put it in khurak/.env:
#     EVON_BASE_URL=https://<random>.trycloudflare.com
#     EVON_MODEL=evon
# then restart the Khurak backend. The header badge turns "Evon v3.3 · online".
#
# Why GGUF + llama.cpp: the BF16 weights are ~60 GB; the Q4_K_M quant (~18 GB) fits across
# two 16 GB T4s. Khurak only needs short JSON answers, so 8k context is plenty.
# =============================================================================================

# --- CELL 1: build llama.cpp with CUDA (nemotron_h_moe needs a recent build) ----------------
# !git clone --depth 1 https://github.com/ggml-org/llama.cpp /kaggle/working/llama.cpp
# !cd /kaggle/working/llama.cpp && cmake -B build -DGGML_CUDA=ON -DLLAMA_CURL=OFF \
#     && cmake --build build --config Release -j 4 --target llama-server

# --- CELL 2: download the quantised Evon weights ---------------------------------------------
# !pip -q install -U "huggingface_hub[hf_transfer]"
# import os; os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
# from huggingface_hub import hf_hub_download
# GGUF = hf_hub_download("luminenio/gnani-evon-v3.3-30B-A3B-GGUF",
#                        "gnani-evon-v3.3-30B-A3B-Q4_K_M.gguf", local_dir="/kaggle/working/models")
# print(GGUF)

# --- CELL 3: start an OpenAI-compatible server on both GPUs ----------------------------------
# import subprocess, time
# server = subprocess.Popen([
#     "/kaggle/working/llama.cpp/build/bin/llama-server", "-m", GGUF, "--alias", "evon",
#     "--host", "0.0.0.0", "--port", "8080", "-ngl", "999", "--split-mode", "layer",
#     "-c", "8192", "--jinja", "--parallel", "2",
#     "--api-key", "khurak-demo-key-change-me",
# ], stdout=open("/kaggle/working/server.log", "w"), stderr=subprocess.STDOUT)
# for _ in range(120):
#     time.sleep(5)
#     if "server is listening" in open("/kaggle/working/server.log").read(): print("Evon ready"); break
# !tail -5 /kaggle/working/server.log

# --- CELL 4: expose it with a free Cloudflare quick tunnel -----------------------------------
# !wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
# !chmod +x cloudflared
# import re, subprocess, time
# tun = subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://localhost:8080"],
#                        stderr=subprocess.PIPE, text=True)
# for line in tun.stderr:
#     m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
#     if m:
#         print("EVON_BASE_URL=" + m.group(0)); print("EVON_API_KEY=khurak-demo-key-change-me"); break

# --- CELL 5: sanity check (Hindi, reasoning off) ---------------------------------------------
# import requests
# r = requests.post("http://localhost:8080/v1/chat/completions",
#     headers={"Authorization": "Bearer khurak-demo-key-change-me"},
#     json={"model": "evon", "max_tokens": 120, "temperature": 0,
#           "chat_template_kwargs": {"enable_thinking": False},
#           "messages": [{"role": "user", "content": "Translate to English: मेरी आँखें पीली हो गई हैं"}]})
# print(r.json()["choices"][0]["message"]["content"])
#
# Keep the notebook running while you demo. Kaggle sessions stop after ~12 h of runtime.
