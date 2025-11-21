"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Core app schemas for the Instagram automation prototype

class Account(BaseModel):
    ownerId: Optional[str] = Field(None, description="Owner user id in this app")
    name: str = Field(..., description="Friendly account name")
    fbAppId: Optional[str] = Field(None, description="Facebook App ID")
    pageId: Optional[str] = Field(None, description="Connected Facebook Page ID")
    igBusinessId: Optional[str] = Field(None, description="Instagram Business Account ID")
    tokens: Optional[Dict[str, Any]] = Field(default=None, description="Access tokens and metadata (encrypted in prod)")
    webhookSecret: Optional[str] = Field(None, description="Webhook verify token/secret")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Misc settings like quiet hours, opt-out keywords")

class FlowNode(BaseModel):
    id: str
    type: str
    data: Dict[str, Any] = Field(default_factory=dict)

class FlowEdge(BaseModel):
    id: str
    source: str
    target: str
    condition: Optional[str] = None

class Flow(BaseModel):
    accountId: str
    name: str
    description: Optional[str] = None
    keywords: List[str] = Field(default_factory=list, description="Keywords that trigger this flow from comments")
    nodes: List[FlowNode] = Field(default_factory=list)
    edges: List[FlowEdge] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active")
    version: int = Field(default=1)

class Assignment(BaseModel):
    accountId: str
    igMediaId: str
    flowId: str

class IGUser(BaseModel):
    accountId: str
    igUserId: str
    username: Optional[str] = None
    followerStatus: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    lastInteractionAt: Optional[datetime] = None

class Message(BaseModel):
    role: str = Field(..., description="agent or user")
    text: str
    ts: Optional[datetime] = None

class Conversation(BaseModel):
    accountId: str
    igUserId: str
    messages: List[Message] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)
    lastMessageAt: Optional[datetime] = None

class Event(BaseModel):
    type: str
    accountId: str
    payload: Dict[str, Any] = Field(default_factory=dict)

# Keep example schemas for reference (not used by the app directly)
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
