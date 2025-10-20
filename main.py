from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Permitir cualquier origen para desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado global de señalización
SIGNALING_STATE = {
    "offer": None,
    "answer": None
}

# Cuando la Pi envía la oferta
@app.post("/offer")
async def post_offer(request: Request):
    data = await request.json()
    # Limpiar la respuesta anterior
    SIGNALING_STATE["answer"] = None
    SIGNALING_STATE["offer"] = data
    return {"status": "ok"}

# Cuando el navegador obtiene la oferta
@app.get("/offer")
async def get_offer():
    if SIGNALING_STATE["offer"]:
        return JSONResponse(content=SIGNALING_STATE["offer"])
    return JSONResponse(content={"status": "pending"}, status_code=404)

# Cuando el navegador envía la respuesta
@app.post("/answer")
async def post_answer(request: Request):
    data = await request.json()
    SIGNALING_STATE["answer"] = data
    return {"status": "ok"}

# Cuando la Pi hace polling para obtener la respuesta
@app.get("/answer")
async def get_answer():
    if SIGNALING_STATE["answer"]:
        return JSONResponse(content=SIGNALING_STATE["answer"])
    return JSONResponse(content={"status": "pending"}, status_code=404)
