import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, getlogname, getholdingsname
from helpers import getuser, startover, getcash, buyshares, sellshares, valueheld, logchange
from helpers import lastquote, lastbought


# Configure application
app = Flask(__name__)


# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    #find name of holdings DB
    holdings=valueheld(db)
    currentcash=getcash(db)
    return render_template("index.html", data=holdings,cash=currentcash)


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    """Modify Account Settings"""
    if request.method == "POST":

        #Ensure current-password was provided
        if not request.form.get("current-password"):
            return apology("must provide password", 403)

        #Check current-password is correct
        currentusername=getuser(db)
        getpass = db.execute("SELECT * FROM users WHERE username = :username",
                          username=currentusername)
        if not check_password_hash(getpass[0]["passhash"], request.form.get("current-password")):
            return apology("current password incorrect", 403)

        #Ensure username was submitted
        if request.form.get("username"):

            #see if username already exists:
            newusername=request.form.get("username")
            checkusername=db.execute("SELECT * FROM users WHERE username = :username",
                          username=newusername)
            if len(checkusername) >= 1:
                print(checkusername)

                #tell if it's their name already
                if currentusername is newusername:
                    return apology("already your name",403)

                #tell if someone else has that name
                else:
                    return apology("username already taken", 403)

            #if username doesn't already exist, make it theirs!
            else:

                 #update holdings table name
                holdings = "_holdings"
                currentholdingsname=getholdingsname(db)
                newholdingsname = request.form.get("username")+holdings
                db.execute("ALTER TABLE :currentname RENAME TO :newname",
                          currentname=currentholdingsname, newname=newholdingsname)

                #update user actions log name
                log = "_log"
                currentlogname=getlogname(db)
                newlogname = request.form.get("username")+log
                db.execute("ALTER TABLE :currentname RENAME TO :newname",
                          currentname=currentlogname, newname=newlogname)

                #update users table
                db.execute("UPDATE users SET username = :newusername WHERE id=:session",
                          newusername=newusername, session=session["user_id"])

                #log change
                logchange("username_change",db)
                userupdate=1

        #determine if a new password field has an entry
        if request.form.get("new-password") or request.form.get("confirm-password"):

            #ensure new password entries match:

            #specific error to confirm name change was successful, though password change failed
            if request.form.get("new-password") != request.form.get("confirm-password") and userupdate==1:
                odderror="name changed to "+newusername+" password change failed: must match!"
                return apology(odderror, 403)

            #error for just password fail
            elif request.form.get("new-password") != request.form.get("confirm-password"):
                return apology("password fail: password and confirm password must match", 403)

            #otherwise, update the password
            else:
                #update password
                db.execute("UPDATE users SET passhash = :newpass WHERE id=:session",
                          newpass=generate_password_hash(request.form.get("new-password")), session=session["user_id"])

                #log password change
                logchange("password_change", db)

        # Redirect user to home page
        return redirect("/")

    #User reached via GET (link/redirect)
    else:
        return render_template("account.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stocks"""
    if request.method == "POST":

        #verify user provided ticker symbol
        if not request.form.get("symbol"):
            return apology("symbol needed",403)

        #verify user provided quantity to sell
        elif not request.form.get("qty"):
            return apology("qty needed",403)

        #tests passed: let's sell!
        else:

            #cleanup variables
            sym=request.form.get("symbol")
            sym=sym.upper()
            qty=int(request.form.get("qty"))

            #sellshares function executes the sale
            sold=sellshares(sym,qty,db)
            if sold == True:
                return redirect("/")
            else:
                return apology("ain't got enough")

    else:
        #variables to display holdings & cash while considering sale
        holdings=valueheld(db)
        currentcash=getcash(db)
        return render_template("sell.html", data=holdings,cash=currentcash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        #verify symbold & qty fields were filled out properly
        if not request.form.get("symbol"):
            return apology("must provide ticker symbol to purchase", 403)
        elif not request.form.get("qty"):
            return apology("must provide qty to purchase", 403)
        elif not request.form.get("qty").isdigit():
            return apology("must provide valid qty to purchase", 403)
        else:

            #clean up vars
            sym = request.form.get("symbol")
            sym = sym.upper()
            qty = int(request.form.get("qty"))

            #verify ticker symbol is real
            if lookup(sym) == None:
                return apology("invalid ticker symbol", 403)

            #execute the sale
            else:
                bought=buyshares(sym,qty,db)
                if bought == True:
                    return redirect("/buy_success")
                elif bought == 999:
                    return apology("not enough ca$h", 403)
                else:
                    return apology("unknown", 403)
    else:
        #variables to show current cash & holdings
        cash=getcash(db)
        holdings=valueheld(db)
        return render_template("buy.html", data=holdings, cash=cash)


@app.route("/buy_from_quote", methods=["GET", "POST"])
@login_required
def buy_from_quote():
    """Show quote & qty purchase option"""

    #Get relevant quote information from db
    quote=lastquote(db)

    if request.method == "POST":

        #verify qty field was filled out properly
        if not request.form.get("qty"):
            return apology("must provide qty to purchase", 403)
        elif not request.form.get("qty").isdigit():
            return apology("must provide valid qty to purchase", 403)

        #execute the purchase
        else:
            sym=quote[0]['symbol']
            qty=int(request.form.get("qty"))
            bought=buyshares(sym,qty,db)
            if bought == True:
                return redirect("/buy_success")
            elif bought == 999:
                return apology("not enough ca$h", 403)
            else:
                return apology("unknown", 403)
    else:
        #show relevant info
        cash=getcash(db)
        return render_template("buy_from_quote.html",symbol=quote[0]['symbol'],price=quote[0]['price'], cash=cash)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        else:
            # Query database for username
            rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

            # Ensure username exists and password is correct
            if len(rows) != 1 or not check_password_hash(rows[0]["passhash"], request.form.get("password")):
                return apology("invalid username and/or password", 403)

            else:
                # Remember which user has logged in
                session["user_id"] = rows[0]["id"]

                # Redirect user to home page
                return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        #verify symbol entry present
        if not request.form.get("symbol"):
            return apology("please enter ticker symbol", 403)

        #lookup the symbol
        else:
            sym=(request.form.get("symbol"))
            sym=sym.upper()
            if lookup(sym) != None:
                result = lookup(sym)

                #log quote
                logname = getlogname(db)
                db.execute("INSERT INTO :logname (username, datetime, action,symbol,price) VALUES(:username, DATETIME('now'), 'quote', :symbol, :price)",
                          logname=logname, username=getuser(db), symbol = result['symbol'], price = result['price'])

                #get current cash to pass to result page for user consideration
                currentcash=getcash(db)

                return render_template("quote_result.html", name = result['name'], price = result['price'], symbol = result['symbol'], cash=currentcash)

            #if lookup(sym) is bad, means ticker was invalid
            else:
                return apology("invalid ticker symbol", 403)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        #Ensure username doesn't exist yet
        if len(rows) >= 1:
            return apology("username already taken", 403)

        #Ensure passwords match:
        elif request.form.get("password") != request.form.get("confirm-password"):
            return apology("password and confirm password must match", 403)

        else:
            #Add the user & password
            db.execute("INSERT INTO users (username, passhash) VALUES(:username, :newhash)",
                          username=request.form.get("username"), newhash=generate_password_hash(request.form.get("password")))

            #Create user holdings
            holdings = "_holdings"
            holdingsname = request.form.get("username")+holdings
            db.execute("CREATE TABLE :holdingstable (holdingid INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, symbol TEXT NOT NULL UNIQUE, qty INTEGER NOT NULL)",
                          holdingstable=holdingsname)

            #Create user actions log
            log = "_log"
            logname = request.form.get("username")+log
            db.execute("CREATE TABLE :userlogtable (useractionid INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, datetime TEXT, action TEXT NOT NULL, symbol TEXT, price REAL, qty INTEGER)",
                          userlogtable=logname)

            #log account creation
            db.execute("INSERT INTO :logname (username, datetime, action) VALUES(:username, DATETIME('now'), 'account_creation')",
                          username=request.form.get("username"), logname=logname)

            # Query database for username
            rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

            # Remember which user has logged in
            session["user_id"] = rows[0]["id"]
            print(getuser(db))

            # Redirect user to home page
            return redirect("/")

    #User reached via GET (link/redirect)
    else:
        return render_template("register.html")


@app.route("/buy_success", methods=["GET", "POST"])
@login_required
def buy_success():
    """Show purchase confirmation"""
    #Get most recent purchase information from db
    bought=lastbought(db)
    return render_template("buy_success.html", qty=bought[0]['qty'], symbol=bought[0]['symbol'], price=bought[0]['price'])


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    logname=getlogname(db)
    username=getuser(db)
    log=db.execute("SELECT datetime,action,symbol,price,qty FROM :userlog",
                          userlog=logname)
    return render_template("history.html", dblog=log, username=username)


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/mrclean", methods=["GET","POST"])
def mrclean():
    """Wipe DB Data"""
    if request.method == "POST":

        cleanpass = db.execute("SELECT * FROM mrclean")

        #if mrclean password exists
        if len(cleanpass) == 1:

            #ensure entry in password field
            if not request.form.get("password"):
                return apology("password must be set", 403)

            #if password incorrect
            if not check_password_hash(cleanpass[0]["passhash"], request.form.get("password")):
                return apology("incorrect password", 403)

            #if password correct
            else:
                startover(db)
                return render_template("clean.html")

        #if mrclean password doesn't exist
        else:
            #ensure entry in password field
            if not request.form.get("password"):
                return apology("password missing", 403)
            else:
                hashed=generate_password_hash(request.form.get("password"))
                db.execute("INSERT INTO mrclean (passhash) VALUES(:hashed)",
                          hashed=hashed)
                startover(db)
                return render_template("clean.html")

    else:
        #does a mrclean password exist yet?
        cleanpass = db.execute("SELECT * FROM mrclean")

        #if so, ask user to enter it
        if len(cleanpass) == 1:
            instruction="Enter Password"
            button="Clean"

        #if not, ask user to set it
        else:
            instruction="Set Password"
            button="Set"
        return render_template("mrclean.html",instruction=instruction, button=button)


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)