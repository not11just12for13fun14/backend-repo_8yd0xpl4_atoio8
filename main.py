import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import db, create_document, get_documents
from schemas import Account, Flow, Assignment, IGUser, Conversation, Event

app = FastAPI(title="IG Comment-to-DM Automation Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "IG Automation Backend Running"}

# --- Health & schema ---
class SchemaResponse(BaseModel):
    collections: List[str]
    models: Dict[str, Any]

@app.get("/schema", response_model=SchemaResponse)
def get_schema():
    # Return a minimal schema map for viewer/tools
    from schemas import Account, Flow, Assignment, IGUser, Conversation, Event, User, Product
    return {
        "collections": [
            "account", "flow", "assignment", "iguser", "conversation", "event",
            "user", "product"
        ],
        "models": {
            "Account": Account.model_json_schema(),
            "Flow": Flow.model_json_schema(),
            "Assignment": Assignment.model_json_schema(),
            "IGUser": IGUser.model_json_schema(),
            "Conversation": Conversation.model_json_schema(),
            "Event": Event.model_json_schema(),
            "User": User.model_json_schema(),
            "Product": Product.model_json_schema(),
        }
    }

# --- Mock auth/connect endpoints ---
class ConnectRequest(BaseModel):
    account_name: str

@app.post("/connect")
def connect_ig(req: ConnectRequest):
    # In a real app: start FB Login/OAuth; here we just create an Account doc
    acc = Account(name=req.account_name, settings={"opt_out": ["STOP", "UNSUBSCRIBE"]})
    acc_id = create_document("account", acc)
    return {"status": "connected", "accountId": acc_id}

# --- Flow management ---
@app.post("/flows")
def create_flow(flow: Flow):
    flow_id = create_document("flow", flow)
    return {"id": flow_id}

@app.get("/flows")
def list_flows(accountId: Optional[str] = Query(None)):
    fl = get_documents("flow", {"accountId": accountId} if accountId else {})
    # Convert ObjectIds to strings if present
    for f in fl:
        f["_id"] = str(f.get("_id"))
    return fl

class AssignRequest(BaseModel):
    accountId: str
    igMediaId: str
    flowId: str

@app.post("/assign")
def assign_flow(req: AssignRequest):
    aid = create_document("assignment", req.model_dump())
    return {"id": aid}

# --- Webhook simulation endpoints ---
# Meta verification (GET with hub.challenge)
@app.get("/webhook")
def verify_webhook(hub_mode: str = Query(None, alias="hub.mode"), hub_token: str = Query(None, alias="hub.verify_token"), hub_challenge: str = Query(None, alias="hub.challenge")):
    if hub_mode == "subscribe" and hub_token:
        return int(hub_challenge or 0)
    raise HTTPException(status_code=403, detail="Verification failed")

class CommentEvent(BaseModel):
    accountId: str
    igMediaId: str
    igUserId: str
    username: Optional[str] = None
    text: str

@app.post("/webhook/comment")
def on_comment(ev: CommentEvent):
    # 1) Find assignment for this media
    assigns = get_documents("assignment", {"igMediaId": ev.igMediaId, "accountId": ev.accountId})
    if not assigns:
        return {"processed": False, "reason": "No flow assigned"}

    assignment = assigns[0]

    # 2) Load flow and check keyword triggers
    flow_docs = get_documents("flow", {"_id": assignment["flowId"]}) if assignment.get("flowId") else []
    if not flow_docs:
        # fallback: list by account and pick first
        flow_docs = get_documents("flow", {"accountId": ev.accountId})
    if not flow_docs:
        return {"processed": False, "reason": "Flow not found"}

    flow = flow_docs[0]
    kws = [k.lower() for k in (flow.get("keywords") or [])]
    if kws and not any(k in ev.text.lower() for k in kws):
        return {"processed": False, "reason": "Keyword not matched"}

    # 3) Upsert IG user
    users = get_documents("iguser", {"igUserId": ev.igUserId, "accountId": ev.accountId})
    if users:
        user_doc = users[0]
    else:
        igu = IGUser(accountId=ev.accountId, igUserId=ev.igUserId, username=ev.username)
        create_document("iguser", igu)
        user_doc = igu.model_dump()

    # 4) Create conversation message log
    convo = {
        "accountId": ev.accountId,
        "igUserId": ev.igUserId,
        "messages": [
            {"role": "user", "text": f"Commented: {ev.text}"},
            {"role": "agent", "text": "Hey! Thanks for commenting. If you enjoy this, consider following us for more. Reply with 'I followed' to continue."},
        ],
    }
    create_document("conversation", convo)

    # 5) Emit event
    create_document("event", Event(type="comment_trigger", accountId=ev.accountId, payload=ev.model_dump()))

    return {"processed": True, "action": "asked_follow", "next": "wait_for_dm_reply"}

class DMEvent(BaseModel):
    accountId: str
    igUserId: str
    text: str

@app.post("/webhook/dm")
def on_dm(ev: DMEvent):
    t = ev.text.strip().lower()
    if t in ["i followed", "followed", "yes"]:
        # deliver promised asset placeholder
        msg = "Awesome! Here is your promised item: https://example.com/asset?token=demo"
        create_document("event", Event(type="deliver_asset", accountId=ev.accountId, payload=ev.model_dump()))
        # Log conversation message
        create_document("conversation", {
            "accountId": ev.accountId,
            "igUserId": ev.igUserId,
            "messages": [
                {"role": "agent", "text": msg}
            ]
        })
        return {"delivered": True}
    elif t in ["stop", "unsubscribe"]:
        create_document("event", Event(type="opt_out", accountId=ev.accountId, payload=ev.model_dump()))
        return {"opted_out": True}
    else:
        create_document("event", Event(type="dm_other", accountId=ev.accountId, payload=ev.model_dump()))
        return {"ack": True, "hint": "Reply 'I followed' to proceed or 'STOP' to opt out."}

# --- Analytics summaries ---
@app.get("/analytics/summary")
def analytics_summary(accountId: Optional[str] = Query(None)):
    # Simple counts
    from bson import ObjectId
    filt = {"accountId": accountId} if accountId else {}
    counts = {
        "comments_processed": len(get_documents("event", {**filt, "type": "comment_trigger"})),
        "assets_delivered": len(get_documents("event", {**filt, "type": "deliver_asset"})),
        "opt_outs": len(get_documents("event", {**filt, "type": "opt_out"})),
        "conversations": len(get_documents("conversation", filt)),
    }
    return counts

# Keep the original /test endpoint for DB diagnostics
@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
