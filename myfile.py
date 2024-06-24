from fastapi import FastAPI, Request, Depends, Form,status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import psycopg2, psycopg2.extras
from datetime import date
from scripts.config.config import *
from scripts.auth import *
from scripts.models import get_db, User
from scripts.validation.forms import UserCreateForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

api = FastAPI()

api.mount("/static", StaticFiles(directory="/app/static"), name="static")

templates = Jinja2Templates(directory="/app/templates")

@api.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/login", status_code=303)

@api.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@api.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@api.post("/register")
async def register(
    request : Request, 
    db: Session = Depends(get_db)
    ):
    form = UserCreateForm(request)
    await form.load_data()
    if await form.is_valid():
        existing_user = get_user_by_email(email=form.email, db=db)
        if existing_user:
            form.__dict__.get("errors").append("This email is already in use")
            return templates.TemplateResponse("register.html", form.__dict__)

        user = UserCreate(username=form.username, email=form.email, password=form.password, phone=form.phone)
        try:
            user = create_user(user=user, db=db)
            return RedirectResponse("/?msg=Successfully-Registered", status_code=status.HTTP_302_FOUND)
        except IntegrityError:
            form.__dict__.get("errors").append("Duplicate username or email")
            return templates.TemplateResponse("register.html", form.__dict__)
    return templates.TemplateResponse("register.html", form.__dict__)


@api.get("/stocks")
async def stocks(request: Request):

    stock_filter = request.query_params.get('filter', False)

    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if stock_filter == 'stock':
        cursor.execute("""
            SELECT id, symbol, name from stock where is_etf is False
        """)
    elif stock_filter == 'etf':
        cursor.execute("""
            SELECT id, symbol, name from stock where is_etf is True
        """)
    elif stock_filter == 'new_closing_highs':
        # day = "2022-08-19"
        day = date.today().isoformat()
        # WHERE date = (SELECT MAX(date) FROM stock_price);
        cursor.execute("""
        select * from (
            select stock_id, symbol, name, max(close) as mx
            from stock_price
            join stock on stock.id = stock_price.stock_id
            group by stock_id, symbol, name) q
        join stock_price on stock_price.stock_id = q.stock_id and q.mx = stock_price.close
        where datetime = %s
        """, (day,))
    elif stock_filter == 'new_closing_lows':
        # day = "2022-09-20"
        day = date.today().isoformat()
        cursor.execute("""
        select * from (
            select stock_id, symbol, name, min(close) as close
            from stock_price
            join stock on stock.id = stock_price.stock_id
            group by stock_id, symbol, name) q
        join stock_price on stock_price.stock_id = q.stock_id and q.close = stock_price.close
        where datetime = %s
        """, (day,))
    else:
        cursor.execute("SELECT id, symbol, name from stock ORDER BY symbol")

    rows = cursor.fetchall()

    return templates.TemplateResponse("stocks.html", {"request": request, "stocks": rows})

@api.get("/stock/{symbol}")
async def stock_detail(request: Request, symbol):
    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT *
        FROM stock
        JOIN company_info ON stock_id = id
        WHERE symbol = %s
    """, (symbol,))

    stock = cursor.fetchone()
    print(symbol)

    cursor.execute("""
        SELECT * FROM stock_price WHERE stock_id = %s
        ORDER BY datetime DESC
    """, (stock["id"],))

    prices = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM strategy
    """)

    strategies = cursor.fetchall()

    return templates.TemplateResponse("stock_detail.html", {"request": request, "stock": stock, "prices": prices, "strategies": strategies})

@api.post("/apply_strategy")
def apply_strategy(strategy_id: int = Form(...), stock_id: int = Form(...)):
    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        INSERT INTO stock_strategy VALUES (%s, %s)
    """, (stock_id, strategy_id,))

    connection.commit()

    return RedirectResponse(url=f"/strategy/{strategy_id}", status_code=303)

@api.post("/delete_strategy")
def apply_strategy(strategy_id: int = Form(...), stock_id: int = Form(...)):
    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        DELETE FROM stock_strategy
        WHERE stock_id = %s AND strategy_id = %s
    """, (stock_id, strategy_id,))

    connection.commit()

    return RedirectResponse(url=f"/strategy/{strategy_id}", status_code=303)

@api.get("/strategy/{strategy_id}")
async def strategy(request: Request, strategy_id):
    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT id, name FROM strategy WHERE id = %s
    """, (strategy_id,))

    strategy = cursor.fetchone()

    cursor.execute("""
        SELECT id, symbol, name, exchange 
        FROM stock 
        JOIN stock_strategy ON stock.id = stock_strategy.stock_id
        WHERE strategy_id = %s
    """, (strategy_id,))

    stocks = cursor.fetchall()

    return templates.TemplateResponse("strategy.html", {"request": request, "stocks": stocks, "strategy": strategy})


@api.get("/strategies")
async def strategies(request: Request):

    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT * FROM strategy
    """)

    strategies = cursor.fetchall()

    return templates.TemplateResponse("strategies.html", {"request": request, "strategies": strategies})

@api.get("/performance", response_class=HTMLResponse)
async def index(request: Request):
    connection = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cursor.execute("""
        SELECT * FROM gainloss
        ORDER BY close_date DESC
    """)

    gainloss = cursor.fetchall()

    cursor.execute("""
        select
        count(case when gain_loss > 0 then 1 end) AS WinCount,
        count(case when gain_loss < 0 then 1 end) AS LossCount
        from gainloss
    """)

    stats = cursor.fetchone()

    cursor.execute("""
        select balance from balance
        order by date DESC
        limit 1
    """)

    balance = cursor.fetchone()

    return templates.TemplateResponse("performance.html", {"request": request, "gainloss": gainloss, "stats": stats, "balance": balance})