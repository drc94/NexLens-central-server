from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI()

offer_sdp = None
answer_sdp = None

@app.post("/offer")
async def post_offer(request: Request):
    global offer_sdp
    offer_sdp = await request.json()
    return PlainTextResponse("Offer received")

@app.get("/offer")
async def get_offer():
    if offer_sdp is None:
        return PlainTextResponse("No offer yet", status_code=404)
    return JSONResponse(offer_sdp)

@app.post("/answer")
async def post_answer(request: Request):
    global answer_sdp
    answer_sdp = await request.json()
    return PlainTextResponse("Answer received")

@app.get("/answer")
async def get_answer():
    if answer_sdp is None:
        return PlainTextResponse("No answer yet", status_code=404)
    return JSONResponse(answer_sdp)
