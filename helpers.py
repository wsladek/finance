import requests
import urllib.parse

from flask import redirect, render_template, request, session
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/0.12/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def lookup(symbol):
    """Look up quote for symbol."""

    # Contact API
    try:
        response = requests.get(f"https://api.iextrading.com/1.0/stock/{urllib.parse.quote_plus(symbol)}/quote")
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        quote = response.json()
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError):
        return None


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"

def lastquote(db):
    """Retrieve the last quote from the database"""
    quote=db.execute("SELECT symbol, price FROM :logname WHERE useractionid = (SELECT MAX(useractionid) FROM :logname WHERE action = 'quote')",
                          logname=getlogname(db))
    return quote

def lastbought(db):
    """Retrieve the last purchase recorded to the database"""
    bought=db.execute("SELECT symbol, price, qty FROM :logname WHERE useractionid = (SELECT MAX(useractionid) FROM :logname WHERE action = 'buy')",
                          logname=getlogname(db))
    return bought

def getcash(db):
    """Lookup the current cash held by the user"""
    cashdict=db.execute("SELECT cash FROM users WHERE id=:sessionid",
                        sessionid=session["user_id"])
    cash=cashdict[0]['cash']
    cash=round(cash,2)
    return cash

def getlogname(db):
    """Determine what the log table name should be/is for current user"""
    username=db.execute("SELECT username FROM users WHERE id=:sessionid",
                          sessionid=session["user_id"])
    log = "_log"
    logname = username[0]["username"]+log
    return logname

def getholdingsname(db):
    """Determine what holdings table name should be/is for current user"""
    username=db.execute("SELECT username FROM users WHERE id=:sessionid",
                          sessionid=session["user_id"])
    holdings = "_holdings"
    holdingsname = username[0]["username"]+holdings
    return holdingsname

def getuser(db):
    """Retrieve username based on current session id"""
    fromdb=db.execute("SELECT username FROM users WHERE id=:sessionid",
                          sessionid=session["user_id"])
    username=fromdb[0]['username']
    return username

def buyshares(sym,qty,db):
    """Function to execute a purchase, provided Ticker Symbol & QTY"""

    #verify symbol is good
    if lookup(sym) == None:
        return apology("invalid ticker symbol", 403)

    else:
        #get necessary data
        result = lookup(sym)
        holdingsname=getholdingsname(db)
        username=getuser(db)
        logname = getlogname(db)

        #verify user has enough dough
        cost = result['price']*qty
        if getcash(db) < cost:
            return 999

        #execute the purchase
        else:
            #check if holdings already
            exists=db.execute("SELECT symbol FROM :holdings WHERE symbol=:symbol",
                            holdings=holdingsname, symbol=sym)

            #if there are holdings already, we'll update qty
            if exists:
                db.execute("UPDATE :holdings SET qty=qty+:new WHERE symbol=:symbol",
                          holdings=holdingsname, symbol=sym, new=qty)

            #if there aren't holdings already, we'll create a new row
            else:
                db.execute("INSERT INTO :holdings (username, symbol, qty) VALUES(:username, :symbol, :qty)",
                          holdings=holdingsname, username=username, symbol=sym, qty=qty)

            #subtract total price from cash
            db.execute("UPDATE users SET cash=cash-:cost WHERE id=:sessionid",
                          cost=cost, sessionid=session["user_id"])

            #add action to log
            db.execute("INSERT INTO :logname (username, datetime, action, symbol, price, qty) VALUES(:username, DATETIME('now'), 'buy', :symbol, :price, :qty)",
                          logname=logname, username=username, symbol=sym, price=result['price'], qty=qty)
            return True



def sellshares(sym,qty,db):
    """Function to execute a sale, provided Ticker Symbol & QTY"""
    #Verify Possession (it's 9/10 of the law)
    exists=db.execute("SELECT symbol FROM :holdings WHERE symbol=:symbol",
                            holdings=getholdingsname(db), symbol=sym)
    inposs=db.execute("SELECT qty FROM :holdings WHERE symbol=:symbol",
                            holdings=getholdingsname(db), symbol=sym)

    #check that sufficient shares are available to sell
    if len(exists)==1 and inposs[0]['qty'] >= qty:

        #Execute Sale
        holdingsname=getholdingsname(db)
        username=getuser(db)
        logname = getlogname(db)
        result = lookup(sym)
        value = result['price']*qty

        #update holdings db with adjusted share quantity
        db.execute("UPDATE :holdings SET qty=qty-:new WHERE symbol=:symbol",
                  holdings=getholdingsname(db), symbol=sym, new=qty)

        #update cash with proceeds from sale
        db.execute("UPDATE users SET cash=cash+:value WHERE id=:sessionid",
                          value=value, sessionid=session["user_id"])

        #add action to log
        db.execute("INSERT INTO :logname (username, datetime, action, symbol, price, qty) VALUES(:username, DATETIME('now'), 'sell', :symbol, :price, :qty)",
                          logname=logname, username=username, symbol=sym, price=result['price'], qty=qty)
        return True

    #if insufficient shares available
    else:
        return False


def valueheld(db):
    holdingsname=getholdingsname(db)
    holdings=db.execute("SELECT symbol,qty FROM :holdingstable",
                        holdingstable=holdingsname)

    for i in holdings:
        i.update({'price':''})
        i.update({'value':''})
        for k, v in i.items():
            if k == 'symbol':
                lookedup=lookup(v)
                currentprice=lookedup['price']
                currentvalue=round(currentprice*i['qty'],2)
                i.update({'price':currentprice})
                i.update({'value':currentvalue})
    return holdings

def logchange(changetype,db):
    db.execute("INSERT INTO :logname (username, datetime, action) VALUES(:username, DATETIME('now'), :changetype)",
                          username=getuser(db), logname=getlogname(db), changetype=changetype)

def startover(db):
    db.execute("DELETE FROM users")
    tables=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('users','sqlite_sequence','mrclean')")
    todo=[li['name'] for li in tables]
    for item in todo:
        db.execute("DROP TABLE IF EXISTS :dropme",
                dropme=item)