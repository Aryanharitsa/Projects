from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()

class PromptSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    provider = db.Column(db.String(50), nullable=True)
    model = db.Column(db.String(50), nullable=True)
    params = db.Column(db.Text, nullable=True)  # JSON string
    system_prompt = db.Column(db.Text, nullable=True)
    pkey = db.Column(db.String(100), nullable=True)
    pvariables = db.Column(db.Text, nullable=True)  # JSON string
    json_mode = db.Column(db.Boolean, default=False)
    mode = db.Column(db.String(50), default="universal")

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat(),
            'provider': self.provider,
            'model': self.model,
            'params': json.loads(self.params) if self.params else {},
            'system_prompt': self.system_prompt,
            'pkey': self.pkey,
            'pvariables': json.loads(self.pvariables) if self.pvariables else {},
            'json_mode': self.json_mode,
            'mode': self.mode
        }