from fastmcp import FastMCP
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("My Expense Tracker v2.0")

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)

init_db()

# -------------------------------
# Add Expense
# -------------------------------
@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    '''Add a new expense entry to the database.'''
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid}

# -------------------------------
# Credit Expense
# -------------------------------
@mcp.tool()
def credit_expense(date, amount, category, subcategory="", note=""):
    '''Record a credit (negative expense) entry in the database.'''
    credit_amount = -abs(amount)
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, credit_amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid, "credited": credit_amount}

# -------------------------------
# List Expenses
# -------------------------------
@mcp.tool()
def list_expenses(start_date, end_date):
    '''List expense entries within an inclusive date range.'''
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

# -------------------------------
# Summarize Expenses
# -------------------------------
@mcp.tool()
def summarize(start_date, end_date, category=None):
    '''Summarize expenses by category within an inclusive date range.'''
    with sqlite3.connect(DB_PATH) as c:
        query = (
            """
            SELECT category, SUM(amount) AS total_amount
            FROM expenses
            WHERE date BETWEEN ? AND ?
            """
        )
        params = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY category ORDER BY category ASC"

        cur = c.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

# -------------------------------
# Delete Expenses
# -------------------------------
@mcp.tool()
def delete_expenses(expense_id=None, date=None, start_date=None, end_date=None,
                    category=None, subcategory=None):
    '''Delete expense entries based on filters (id, date, date range, category, subcategory).'''
    query = "DELETE FROM expenses WHERE 1=1"
    params = []

    if expense_id is not None:
        query += " AND id = ?"
        params.append(expense_id)

    if date is not None:
        query += " AND date = ?"
        params.append(date)

    if start_date is not None and end_date is not None:
        query += " AND date BETWEEN ? AND ?"
        params.extend([start_date, end_date])

    if category is not None:
        query += " AND category = ?"
        params.append(category)

    if subcategory is not None:
        query += " AND subcategory = ?"
        params.append(subcategory)

    if not params:
        return {"status": "error", "message": "No filters provided. Refusing to delete all records."}

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(query, params)
        return {"status": "ok", "deleted": cur.rowcount}

# -------------------------------
# Update Expenses
# -------------------------------
@mcp.tool()
def update_expenses(
    expense_id=None,
    start_date=None,
    end_date=None,
    filter_date=None,
    filter_category=None,
    filter_subcategory=None,
    new_date=None,
    new_amount=None,
    new_category=None,
    new_subcategory=None,
    new_note=None,
    dry_run=False
):
    '''Update expense entries with optional dry-run mode.'''
    set_clauses = []
    set_params = []

    if new_date is not None:
        set_clauses.append("date = ?")
        set_params.append(new_date)

    if new_amount is not None:
        set_clauses.append("amount = ?")
        set_params.append(new_amount)

    if new_category is not None:
        set_clauses.append("category = ?")
        set_params.append(new_category)

    if new_subcategory is not None:
        set_clauses.append("subcategory = ?")
        set_params.append(new_subcategory)

    if new_note is not None:
        set_clauses.append("note = ?")
        set_params.append(new_note)

    if not set_clauses:
        return {"status": "error", "message": "No new values provided to update."}

    query = "UPDATE expenses SET " + ", ".join(set_clauses) + " WHERE 1=1"
    where_params = []

    if expense_id is not None:
        query += " AND id = ?"
        where_params.append(expense_id)

    if filter_date is not None:
        query += " AND date = ?"
        where_params.append(filter_date)

    if start_date is not None and end_date is not None:
        query += " AND date BETWEEN ? AND ?"
        where_params.extend([start_date, end_date])

    if filter_category is not None:
        query += " AND category = ?"
        where_params.append(filter_category)

    if filter_subcategory is not None:
        query += " AND subcategory = ?"
        where_params.append(filter_subcategory)

    if not where_params:
        return {"status": "error", "message": "No filters provided. Refusing to update all records."}

    with sqlite3.connect(DB_PATH) as c:
        if dry_run:
            preview_query = "SELECT * FROM expenses WHERE 1=1" + query.split("WHERE 1=1", 1)[1]
            cur = c.execute(preview_query, where_params)
            cols = [d[0] for d in cur.description]
            return {"status": "dry_run", "rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
        else:
            cur = c.execute(query, set_params + where_params)
            return {"status": "ok", "updated": cur.rowcount}

# -------------------------------
# Categories Resource
# -------------------------------
@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    # Read fresh each time so you can edit the file without restarting
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()

# -------------------------------
# Run MCP Server
# -------------------------------

# if __name__ == "__main__":
#     mcp.run()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)