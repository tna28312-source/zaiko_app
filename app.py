from flask import Flask, render_template, request, redirect, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os

app = Flask(__name__)

# PostgreSQL用の接続情報
DB_URL = os.getenv("DATABASE_URL", "postgresql://zaiko_user:GJLpm9lR8t4GaBuKdR7eyiHSgbdTQqUf@dpg-d68188ggjchc73b9og8g-a.oregon-postgres.render.com/zaiko_db_vmw0")

def get_connection():
    # RealDictCursor を使うと fetchall() が辞書型で返る
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    return conn

# =============================
# 商品（materials）一覧
# =============================
@app.route("/materials", methods=["GET", "POST"])
def index():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM materials WHERE is_deleted = 0;")
    materials = cur.fetchall()
    conn.close()
    return render_template("index.html", materials=materials)

# =============================
# 在庫一覧画面<トップページ>
# =============================
@app.route("/")
def home():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.stock_id, m.material_name, m.unit, s.quantity, m.min_stock
        FROM stocks s
        JOIN materials m ON s.material_id = m.material_id
        WHERE s.is_deleted = 0 AND m.is_deleted = 0
        ORDER BY m.material_id
    """)
    stocks = cur.fetchall()
    low_stocks = [s for s in stocks if int(s["quantity"]) <= int(s["min_stock"])]
    conn.close()
    return render_template("stocks.html", stocks=stocks, low_stocks=low_stocks)

# =============================
# 入出庫登録フォーム表示
# =============================
@app.route("/stocks/new")
def new_stock_log():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM materials WHERE is_deleted = 0 ORDER BY material_id")
    materials = cur.fetchall()
    conn.close()
    return render_template("stock_form.html", materials=materials)

# =============================
# 入出庫登録処理
# =============================
@app.route("/stocks/create", methods=["POST"])
def create_stock_log():
    material_id = request.form["material_id"]
    log_type = request.form["type"]
    quantity = float(request.form["quantity"])
    staff = request.form.get("staff", "")
    log_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    cur = conn.cursor()

    # 入出庫履歴へ登録
    cur.execute("""
        INSERT INTO stock_logs (material_id, type, quantity, log_date, staff)
        SELECT %s, %s, %s, %s, %s
        WHERE EXISTS (
            SELECT 1 FROM materials WHERE material_id = %s AND is_deleted = 0
        )
    """, (material_id, log_type, quantity, log_date, staff, material_id))

    # 在庫更新
    if log_type == "in":
        cur.execute("""
            UPDATE stocks
            SET quantity = quantity + %s
            WHERE material_id = %s AND is_deleted = 0
        """, (quantity, material_id))
    else:
        cur.execute("""
            UPDATE stocks
            SET quantity = quantity - %s
            WHERE material_id = %s AND is_deleted = 0
        """, (quantity, material_id))

    conn.commit()
    conn.close()
    return redirect(url_for("home"))

# =============================
# 商品編集フォーム表示＋更新処理
# =============================
@app.route("/materials/<int:id>/edit", methods=["GET", "POST"])
def edit_material(id):
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        unit = request.form["unit"]
        min_stock = request.form.get("min_stock", 0)
        cur.execute("""
            UPDATE materials
            SET material_name = %s, unit = %s, min_stock = %s
            WHERE material_id = %s AND is_deleted = 0
        """, (name, unit, float(min_stock) if min_stock else 0, id))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    cur.execute("SELECT * FROM materials WHERE material_id = %s AND is_deleted = 0", (id,))
    material = cur.fetchone()
    conn.close()
    return render_template("edit_material.html", material=material)

# =============================
# 商品削除（論理削除）
# =============================
@app.route("/materials/<int:id>/delete", methods=["POST"])
def delete_material(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE stocks SET is_deleted = 1 WHERE material_id = %s", (id,))
    cur.execute("UPDATE materials SET is_deleted = 1 WHERE material_id = %s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# =============================
# 商品登録フォーム表示
# =============================
@app.route("/materials/new")
def new_material():
    return render_template("new_material.html")

# =============================
# 商品登録処理
# =============================
@app.route("/materials/create", methods=["POST"])
def create_material():
    name = request.form["name"]
    unit = request.form["unit"]
    min_stock = request.form.get("min_stock", 0)

    conn = get_connection()
    cur = conn.cursor()

    # ★ RETURNING を使ってID取得
    cur.execute("""
        INSERT INTO materials (material_name, unit, min_stock, is_deleted)
        VALUES (%s, %s, %s, 0)
        RETURNING material_id
    """, (name, unit, float(min_stock) if min_stock else 0))

    material_id = cur.fetchone()["material_id"]

    # 初期在庫を作成
    cur.execute(
        "INSERT INTO stocks (material_id, quantity, is_deleted) VALUES (%s, 0, 0)",
        (material_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
