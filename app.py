from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

# DBパス（プロジェクト直下の zaiko.db）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "zaiko.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_connection()

    # ★一時リセット
    conn.execute("DROP TABLE IF EXISTS stock_logs")
    conn.execute("DROP TABLE IF EXISTS stocks")
    conn.execute("DROP TABLE IF EXISTS materials")

    # materials
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            material_id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_name TEXT NOT NULL,
            unit TEXT NOT NULL,
            min_stock INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0
        )
    """)

    # stocks
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            stock_id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (material_id) REFERENCES materials(material_id)
        )
    """)

    # stock_logs ←★これが不足してた
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            log_date TEXT,
            staff TEXT,
            FOREIGN KEY (material_id) REFERENCES materials(material_id)
        )
    """)

    conn.commit()
    conn.close()


    
# ★ここ重要：常に実行される位置
init_db()


# =============================
# 商品（materials）一覧
# =============================
@app.route("/materials", methods=["GET", "POST"])
def index():
    conn = get_connection()
    materials = conn.execute(
        """SELECT * FROM materials WHERE is_deleted = 0;"""
    ).fetchall()
    conn.close()
    return render_template("index.html", materials=materials)


# =============================
# 在庫一覧画面<トップページ>
# =============================
@app.route("/")
def home():
    conn = get_connection()

    stocks = conn.execute(
        """
        SELECT s.stock_id, m.material_name, m.unit, s.quantity, m.min_stock
        FROM stocks s
        JOIN materials m ON s.material_id = m.material_id
        WHERE s.is_deleted = 0 AND m.is_deleted = 0
        ORDER BY m.material_id
        """
    ).fetchall()

    # ★ 在庫不足だけ抽出
    low_stocks = [s for s in stocks if int(s["quantity"]) <= int(s["min_stock"])]

    conn.close()
    return render_template("stocks.html", stocks=stocks, low_stocks=low_stocks)



# =============================
# 入出庫登録フォーム表示
# =============================
@app.route("/stocks/new")
def new_stock_log():
    conn = get_connection()
    materials = conn.execute(
        "SELECT * FROM materials WHERE is_deleted = 0 ORDER BY material_id"
    ).fetchall()
    conn.close()
    return render_template("stock_form.html", materials=materials)


# =============================
# 入出庫登録処理
# =============================
@app.route("/stocks/create", methods=["GET", "POST"])
def create_stock_log():
    if request.method == "POST":
        material_id = request.form["material_id"]
        log_type = request.form["type"]
        quantity = float(request.form["quantity"])
        staff = request.form.get("staff", "")
        log_date = datetime.now().strftime("%Y-%m-%d")

        conn = get_connection()
        cur = conn.cursor()

        # 入出庫履歴へ登録（削除されていない商品のみ許可）
        cur.execute(
            """
            INSERT INTO stock_logs (material_id, type, quantity, log_date, staff)
            SELECT ?, ?, ?, ?, ?
            WHERE EXISTS (
                SELECT 1 FROM materials
                WHERE material_id = ? AND is_deleted = 0
            )
            """,
            (material_id, log_type, quantity, log_date, staff, material_id),
        )

        # 在庫数量を更新（削除されていない在庫のみ）
        if log_type == "in":
            cur.execute(
                """
                UPDATE stocks
                SET quantity = quantity + ?
                WHERE material_id = ? AND is_deleted = 0
                """,
                (quantity, material_id),
            )
        else:
            cur.execute(
                """
                UPDATE stocks
                SET quantity = quantity - ?
                WHERE material_id = ? AND is_deleted = 0
                """,
                (quantity, material_id),
            )

        conn.commit()
        conn.close()

        return redirect(url_for("home"))

    # ===== GET のとき =====
    conn = get_connection()
    materials = conn.execute(
        "SELECT * FROM materials WHERE is_deleted = 0"
    ).fetchall()
    conn.close()

    return render_template("stock_form.html", materials=materials)


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

        cur.execute(
            """
            UPDATE materials
            SET material_name = ?, unit = ?, min_stock = ?
            WHERE material_id = ? AND is_deleted = 0
            """,
            (name, unit, float(min_stock) if min_stock else 0, id),
        )

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    # ===== GET（編集フォーム表示）=====
    material = cur.execute(
        "SELECT * FROM materials WHERE material_id = ? AND is_deleted = 0",
        (id,),
    ).fetchone()

    conn.close()
    return render_template("edit_material.html", material=material)


# =============================
# 商品削除（論理削除）
# =============================
@app.route("/materials/<int:id>/delete", methods=["POST"])
def delete_material(id):
    conn = get_connection()
    cur = conn.cursor()

    # stocks を論理削除
    cur.execute(
        "UPDATE stocks SET is_deleted = 1 WHERE material_id = ?",
        (id,),
    )

    # materials を論理削除
    cur.execute(
        "UPDATE materials SET is_deleted = 1 WHERE material_id = ?",
        (id,),
    )

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

    # materialsテーブルへ登録（削除フラグは0がデフォルト）
    cur.execute(
        """
        INSERT INTO materials (material_name, unit, min_stock, is_deleted)
        VALUES (?, ?, ?, 0)
        """,
        (name, unit, float(min_stock) if min_stock else 0),
    )

    material_id = cur.lastrowid

    # stocksテーブルに初期在庫0で作成
    cur.execute(
        """
        INSERT INTO stocks (material_id, quantity, is_deleted)
        VALUES (?, 0, 0)
        """,
        (material_id,),
    )

    conn.commit()
    conn.close()

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
    
