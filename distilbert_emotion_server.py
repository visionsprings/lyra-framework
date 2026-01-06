from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import torch

# Initialize FastAPI
app = FastAPI()

# Load and quantize RoBERTa emotion model (CPU)
MODEL_NAME = "SamLowe/roberta-base-go_emotions"
print("🔄 Loading and quantizing RoBERTa emotion model (CPU)...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

# Quantize linear layers for CPU
model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
model.to("cpu")

emotion_pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer, device=-1)
print("✅ Emotion model quantized and ready.")

# API input schema
class TextRequest(BaseModel):
    text: str

# Emotion analysis route
@app.post("/analyze")
async def analyze_text(request: TextRequest):
    """Analyzes text for emotions using a quantized pipeline."""
    text = request.text[:512]  # RoBERTa max token limit
    results = emotion_pipeline(text, top_k=None)

    # Sort by score (descending) and round to 5 decimal places
    sorted_results = sorted(results, key=lambda r: r["score"], reverse=True)
    emotions = {r["label"]: round(float(r["score"]), 5) for r in sorted_results}

    return {"emotions": emotions}

# Start server if run directly
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Emotion Server on http://0.0.0.0:8000 ...")
    uvicorn.run("distilbert_emotion_server:app", host="0.0.0.0", port=8000, reload=False)
