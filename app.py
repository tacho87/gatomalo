#!flask/bin/python
from flask import Flask, jsonify,request,abort,render_template, Response, request, redirect, url_for
from sqlalchemy.sql import exists
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
from models.models import *
from modules import db_worker
import os
import json
import requests
import logging
from modules import printer

db_url = os.environ['gatomalo_development']
engine = create_engine(db_url, convert_unicode=True, echo=True)
Base.metadata.create_all(engine)
session_maker = sessionmaker(bind=engine)
#logger = logging.getLogger('flask')
facturas = []

app = Flask(__name__)

def parse_cliente_from_post(post):
    empresa = post.form['factura[cliente][empresa]']
    direccion = post.form['factura[cliente][direccion]']
    telefono = post.form['factura[cliente][telefono]']
    ruc = post.form['factura[cliente][ruc]']
    return { 'empresa':empresa,'direccion':direccion,'telefono':telefono,'ruc':ruc }

def parse_productos_from_post(post):
    nombre = post.form['factura[productos][nombre]']
    cantidad = post.form['factura[productos][cantidad]']
    tasa = post.form['factura[productos][tasa]']
    precio = post.form['factura[productos][precio]']
    return { 'nombre':nombre,'cantidad':cantidad,'tasa':tasa,'precio':precio }

def get_invoice_list():
# Input Variables
    url = 'https://books.zoho.com/api/v3/invoices' #RESTful URL
    authtoken = 'bf3edb14f0a536a594e8c4acf9c0628a' #Authorization token generated by Zoho
    organization_id = '41622462' # organization_id generated by Zoho

    #Get JSON
    auth = {'authtoken':authtoken,'organization_id':organization_id}
    r = requests.get(url,params=auth)
    data = r.json()['invoices']
    return data

def get_invoice_detail(post):
    # Input Variables
    url = 'https://books.zoho.com/api/v3/invoices/'+post #RESTful URL con invoice_id
    authtoken = 'bf3edb14f0a536a594e8c4acf9c0628a' #Authorization token generated by Zoho
    organization_id = '41622462' # organization_id generated by Zoho

    #Get JSON
    auth = {'authtoken':authtoken,'organization_id':organization_id}
    r = requests.get(url,params=auth)
    invoice = r.json()
    return invoice


@app.route('/')
def index():
    invoice_list = get_invoice_list()
    invoice_json = json.dumps(invoice_list)
    return render_template('index.html', invoices=invoice_list)


#falta agregar el argumento para buscar el id del invoice unico y asi encontrar el url correcto.
# def parse_invoice_list():
#     data = get_invoice_list()
#
#     proforma_number = data["invoices"][1]["invoice_number"]
#     fiscal_string = {'invoice_number':proforma_number}
#     return fiscal_string

def translate_product(product):
    if product["tax_percentage"] == 7:
        tasa = 1
    elif product["tax_percentage"] == 0:
        tasa = 0
    elif product["tax_percentage"] == 10:
        tasa = 2
    else:
        tasa = 'error'
    return {"nombre":product['name'],"cantidad":1, "tasa":tasa,"precio":product['item_total']}

def parse_invoice_data(data):
    customer_name = data["invoice"]["customer_name"]
    address = data["invoice"]["billing_address"]["address"]
    phone_number = data["invoice"]["customer_name"]
    productos = [translate_product(p) for p in data["invoice"]["line_items"]]
    return {"factura":{"cliente":{"empresa":"" + customer_name + "","direccion":"" + address + "","telefono":"","ruc":"0"}, "productos":productos}}

@app.route('/create_invoice_json/<invoice_id>')
#falta agregar el argumento para buscar el id del invoice unico y asi encontrar el url correcto.
def create_invoice_json(invoice_id):
    data=get_invoice_detail(invoice_id)
    proforma_number = data["invoice"]["invoice_number"]
    fiscal_json = json.dumps(parse_invoice_data(data), ensure_ascii=False).encode('latin1')

    return Response(fiscal_json,
            mimetype='application/json',
            headers={'Content-Disposition':'attachment;filename='+proforma_number+'.json'})

@app.route('/print_gatomalo/<invoice_id>')
def print_gatomalo(invoice_id):
    data = get_invoice_detail(invoice_id)
    data = parse_invoice_data(data)
    factura,productos,cliente = create_factura(data['factura']['cliente'],data['factura']['productos'])
    fiscal_json = json.dumps(data, ensure_ascii=False).encode('latin1')
    resp = Response(fiscal_json, status=200, mimetype='application/json')
    resp.headers['Link'] = 'http://localhost:5000/facturas'
    return resp

@app.route('/facturas', methods = ['POST'])
def make_factura():
    session = session_maker()
    print(request.json)
    if request.json and 'factura' in request.json:
        productos = request.json['factura']['productos']
        cliente =  request.json['factura']['cliente']
    elif request.form:
        cliente = parse_cliente_from_post(request)
        productos = parse_productos_from_post(request)
    else:
        abort(400)
    try:
        factura,productos,cliente = db_worker.create_factura(session,cliente,productos)
    except Exception as e:
            raise(e)
            session.rollback()
    printer.write_string_to_printer(str(factura))
    return str(factura)

def create_factura(cliente,productos):
    session = session_maker()
    try:
        factura,productos,cliente = db_worker.create_factura(session,cliente,productos)
    except Exception as e:
            raise(e)
            session.rollback()
    printer.write_string_to_printer(str(factura))
    return factura,productos,cliente

@app.route('/nota', methods = ['POST'])
def create_nota():
    session = session_maker()
#   return str(request.form['factura[cliente][empresa]'])
    if request.json and 'nota' in request.json:
        factura_id = request.json['nota']['factura_id']
        legacy_id = request.json['nota']['legacy_id']
    else:
        abort(400)
    try:
        nota = db_worker.create_nota(session,factura_id,legacy_id)
    except Exception as e:
            raise(e)
            session.rollback()
    printer.write_string_to_printer(str(nota))
    return str(nota)
#
@app.route('/facturas', methods = ['GET'])
def get_facturas():
    session = session_maker()
    facturas = db_worker.all_facturas(session)
    return jsonify({f.id:f.to_json() for f in facturas})


@app.route('/print_report', methods = ['POST'])
def print_report():
    if request.form['submit'] == 'Reporte X':
        printer.write_string_to_printer('I0X')
    elif request.form['submit'] == 'Reporte Z':
        printer.write_string_to_printer('I0Z')
    else:
        print('WRONG VALUE')
    return redirect(url_for('.index'))


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0').encode('latin1')
