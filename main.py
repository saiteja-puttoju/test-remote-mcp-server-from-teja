from fastmcp import FastMCP
import os
import aiosqlite
import tempfile
import sqlite3
import json

# Use a writable temp directory for DB
TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("My Expense Tracker v3.0")

# -------------------------------
# Initialize DB (sync, once)
# -------------------------------
def init_db():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")
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
            # Test write access
            c.execute("INSERT OR IGNORE INTO expenses(date, amount, category) VALUES ('2000-01-01', 0, 'test')")
            c.execute("DELETE FROM expenses WHERE category = 'test'")
            print("Database initialized successfully with write access")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

init_db()

# -------------------------------
# Add Expense
# -------------------------------
@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):
    '''Add a new expense entry.'''
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note)
            )
            await c.commit()
            return {"status": "ok", "id": cur.lastrowid}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -------------------------------
# Credit Expense
# -------------------------------
@mcp.tool()
async def credit_expense(date, amount, category, subcategory="", note=""):
    '''Record a credit (negative expense).'''
    credit_amount = -abs(amount)
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, credit_amount, category, subcategory, note)
            )
            await c.commit()
            return {"status": "ok", "id": cur.lastrowid, "credited": credit_amount}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -------------------------------
# List Expenses
# -------------------------------
@mcp.tool()
async def list_expenses(start_date, end_date):
    '''List expenses in a date range.'''
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date)
            )
            cols = [d[0] for d in cur.description]
            rows = await cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -------------------------------
# Summarize Expenses
# -------------------------------
@mcp.tool()
async def summarize(start_date, end_date, category=None):
    '''Summarize expenses by category.'''
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            query = """
                SELECT category,
                       SUM(amount) AS total_amount,
                       COUNT(*) AS count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cur = await c.execute(query, params)
            cols = [d[0] for d in cur.description]
            rows = await cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -------------------------------
# Delete Expenses
# -------------------------------
@mcp.tool()
async def delete_expenses(expense_id=None, date=None, start_date=None, end_date=None,
                          category=None, subcategory=None, dry_run=False):
    '''Delete expenses with filters.'''
    query = "DELETE FROM expenses WHERE 1=1"
    params = []

    if expense_id is not None:
        query += " AND id = ?"
        params.append(expense_id)
    if date is not None:
        query += " AND date = ?"
        params.append(date)
    if start_date and end_date:
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

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            if dry_run:
                preview_query = "SELECT * FROM expenses WHERE 1=1" + query.split("WHERE 1=1", 1)[1]
                cur = await c.execute(preview_query, params)
                cols = [d[0] for d in cur.description]
                rows = await cur.fetchall()
                return {"status": "dry_run", "rows": [dict(zip(cols, r)) for r in rows]}
            else:
                cur = await c.execute(query, params)
                await c.commit()
                return {"status": "ok", "deleted": cur.rowcount}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# -------------------------------
# Update Expenses
# -------------------------------
@mcp.tool()
async def update_expenses(
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
    '''Update expenses with optional dry-run.'''
    set_clauses, set_params = [], []

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
        return {"status": "error", "message": "No new values provided."}

    query = "UPDATE expenses SET " + ", ".join(set_clauses) + " WHERE 1=1"
    where_params = []

    if expense_id is not None:
        query += " AND id = ?"
        where_params.append(expense_id)
    if filter_date is not None:
        query += " AND date = ?"
        where_params.append(filter_date)
    if start_date and end_date:
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

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            if dry_run:
                preview_query = "SELECT * FROM expenses WHERE 1=1" + query.split("WHERE 1=1", 1)[1]
                cur = await c.execute(preview_query, where_params)
                cols = [d[0] for d in cur.description]
                rows = await cur.fetchall()
                return {"status": "dry_run", "rows": [dict(zip(cols, r)) for r in rows]}
            else:
                cur = await c.execute(query, set_params + where_params)
                await c.commit()
                return {"status": "ok", "updated": cur.rowcount}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# -------------------------------
# Categories Resource
# -------------------------------
@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    '''Return categories from file or defaults if missing.'''
    try:
        default_categories = {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other"
            ]
        }
        try:
            with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return json.dumps(default_categories, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Could not load categories: {str(e)}"})

# -------------------------------
# Run MCP Server
# -------------------------------
if __name__ == "__main__":
    # Run as HTTP server (accessible on port 8000)
    mcp.run(transport="http", host="0.0.0.0", port=8000)
    # Or fallback to default transport:
    # mcp.run()