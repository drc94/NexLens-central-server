from aiohttp import web
import json

offer_sdp = None
answer_sdp = None

routes = web.RouteTableDef()

@routes.post("/offer")
async def offer(request):
    global offer_sdp
    offer_sdp = await request.json()
    return web.Response(text="Offer received")

@routes.get("/offer")
async def get_offer(request):
    if offer_sdp is None:
        return web.Response(status=404, text="No offer yet")
    return web.json_response(offer_sdp)

@routes.post("/answer")
async def answer(request):
    global answer_sdp
    answer_sdp = await request.json()
    return web.Response(text="Answer received")

@routes.get("/answer")
async def get_answer(request):
    if answer_sdp is None:
        return web.Response(status=404, text="No answer yet")
    return web.json_response(answer_sdp)

app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    web.run_app(app, port=8080)
