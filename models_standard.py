from app import db
from datetime import datetime, timezone

class MotherCHWAssignment(db.Model):
    __tablename__ = 'mother_chw_assignments'
    id          = db.Column(db.Integer, primary_key=True)
    mother_id   = db.Column(db.Integer, db.ForeignKey('mothers.id', ondelete='CASCADE'), nullable=False)
    mother_name = db.Column(db.String(255), nullable=False)
    chw_id      = db.Column(db.Integer, db.ForeignKey('chws.id', ondelete='CASCADE'), nullable=False)
    chw_name    = db.Column(db.String(255), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    status      = db.Column(db.String(16), nullable=False, default='active')
    assignment_method = db.Column(db.String(32), nullable=False, default='manual')
    reassigned_at = db.Column(db.DateTime)
    reassignment_reason = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('chw_id', 'mother_id', name='unique_chw_mother'),
        db.CheckConstraint("status IN ('active', 'inactive')", name='chk_assignment_status'),
        db.CheckConstraint("assignment_method IN ('manual', 'auto_ward_match')", name='chk_assignment_method'),
    )
