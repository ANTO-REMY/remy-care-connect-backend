from app import db

class MotherCHWAssignment(db.Model):
    __tablename__ = 'mother_chw_assignments'
    id = db.Column(db.Integer, primary_key=True)
    chw_id = db.Column(db.Integer, db.ForeignKey('chws.id'), nullable=False)
    mother_id = db.Column(db.Integer, db.ForeignKey('mothers.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('chw_id', 'mother_id', name='unique_chw_mother'),)
