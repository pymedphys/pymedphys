import os
import sys
import io
import numpy as np
import sqlite3

from sqlalchemy import Column,Integer,Float,String,Binary,ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import DATE
import datetime


Base=declarative_base()

class Patient(Base):
    __tablename__='Patient'
    ID =Column(Integer,primary_key=True)
    Name=Column(String(50),nullable=False)
    LinacID=Column(String(5),nullable=False)
    MeasuredBy=Column(String(15),nullable=True)
    MeasuredOn=Column(DATE)


class Beam(Base):
    __tablename__='Beam'
    ID=Column(Integer,primary_key=True)
    Name=Column(String(15),nullable=True)
    Angle=Column(Float,nullable=True)
    PixelsLessThanOnePercent=Column(Float,nullable=False)
    PixelsLessThanThreePercent=Column(Float,nullable=False)
    PlannedFluence=Column(Binary,nullable=False)
    DeliveredFluence=Column(Binary,nullable=False)
    PatientAttached=relationship(Patient)
    PatientID=Column(Integer,ForeignKey('Patient.ID'))

def NumpyToSQLiteArray(nparray):
    out = io.BytesIO()
    np.save(out, nparray)
    out.seek(0)
    return sqlite3.Binary(out.read())

def SQLiteToNumpyArray(SQLiteArray):
    out = io.BytesIO(SQLiteArray)
    out.seek(0)
    return np.load(out)

#Creates a new database file with Patient,Beam as tables
def CreateEngine():
    engine=create_engine('sqlite:///FluDo.db')
    Base.metadata.create_all(engine)

#CreateEngine()

# engine=create_engine('sqlite:///FluDo.db')
# Base.metadata.bind=engine
#
# DBSession=sessionmaker(bind=engine)
# session=DBSession()
#
# for x in range(1,10,1):
#     NewPt=Patient(ID=x*10,Name='TestPat',MeasuredBy='JKS',MeasuredOn=datetime.datetime.now(),LinacID='LA4')
#     session.add(NewPt)
#     session.commit()

# Flu=np.arange(12).reshape(2,6)
# Flu2=NumpyToSQLiteArray(Flu)


# NewBeam=Beam(ID=1,Name='LtLat',Angle=0.0,PixelsLessThanOnePercent=97.0,PixelsLessThanThreePercent=98.5,PlannedFluence=Flu2,DeliveredFluence=Flu2,PatientID=11111)
# session.add(NewBeam)
# session.commit()

# p1=session.query(Patient).first()
# print(p1.ID)
# print(p1.Name)
# print(p1.MeasuredBy)
# print(p1.MeasuredOn)
# print('------------')
# b1=session.query(Beam).filter(Beam.PatientID==11111).all()
# for x in range(0,np.size(b1),1):
#     Flu=SQLiteToNumpyArray(b1[x].DeliveredFluence)
#     print(Flu)
#
# print(b1.ID)
# print(b1.Name)
# print(b1.Angle)
# print(b1.PixelsLessThanOnePercent)
# print(b1.PixelsLessThanThreePercent)

