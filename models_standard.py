from app import db
from datetime import datetime

class MotherCHWAssignment(db.Model):
    __tablename__ = 'mother_chw_assignments'
    id          = db.Column(db.Integer, primary_key=True)
    mother_id   = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'), nullable=False)
    mother_name = db.Column(db.String(255), nullable=False)
    chw_id      = db.Column(db.Integer, db.ForeignKey('chws.id', ondelete='CASCADE'), nullable=False)
    chw_name    = db.Column(db.String(255), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status      = db.Column(db.String(16), nullable=False, default='active')

    __table_args__ = (
        db.UniqueConstraint('chw_id', 'mother_id', name='unique_chw_mother'),
        db.CheckConstraint("status IN ('active', 'inactive')", name='chk_assignment_status'),
    )
