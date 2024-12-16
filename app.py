from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from rapidfuzz import fuzz  # Import RapidFuzz for fuzzy matching

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

DATABASE = 'gov_ease.db'


# Helper to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows column access by name
    return conn


# Function to query the database and find the best match
def query_response(user_query):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Fetch all queries from the database
        cursor.execute("SELECT DISTINCT query FROM bot_responses")
        all_queries = cursor.fetchall()

        best_match = None
        highest_score = 0
        for query in all_queries:
            query_text = query[0]
            score = fuzz.partial_ratio(user_query, query_text)
            if score > highest_score:
                highest_score = score
                best_match = query_text

        if highest_score > 70:  # Adjust threshold as needed
            cursor.execute("""SELECT response, persons, time 
                              FROM bot_responses WHERE query = ?""", (best_match,))
            results = cursor.fetchall()
            conn.close()
            return best_match, results

        conn.close()
        return None, []
    except Exception as e:
        print(f"Error querying the database: {e}")
        return None, []


# Route: Home Page (Redirects to Login)
@app.route('/')
def index():
    user_name = session.get('user_name')  # Get the user's name from the session
    return render_template('index.html', user_name=user_name)

# Route: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            flash('Login successful!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
    return render_template('login.html')

# Route for the sign-up page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""INSERT INTO users (name, email, password) VALUES (?, ?, ?)""",
                           (name, email, hashed_password))
            conn.commit()
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists. Please log in.', 'danger')
        finally:
            conn.close()

    return render_template('signup.html')


# Route: Admin Page
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user_id' not in session:
        flash('You need to log in to access this page.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        query = request.form['query']
        response = request.form['response']
        persons = request.form['persons']
        time = request.form['time']

        try:
            conn.execute("""
                INSERT INTO bot_responses (query, response, persons, time) 
                VALUES (?, ?, ?, ?)
            """, (query, response, persons, time))
            conn.commit()
            flash('New record added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding record: {e}', 'danger')

    # Fetch all records to display
    data = conn.execute("SELECT * FROM bot_responses").fetchall()
    conn.close()

    return render_template('admin.html', data=data)


# Route: Edit Record
@app.route('/edit/<int:record_id>', methods=['GET', 'POST'])
def edit_record(record_id):
    if 'user_id' not in session:
        flash('You need to log in to access this page.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        query = request.form['query']
        response = request.form['response']
        persons = request.form['persons']
        time = request.form['time']

        try:
            conn.execute("""
                UPDATE bot_responses 
                SET query = ?, response = ?, persons = ?, time = ?
                WHERE id = ?
            """, (query, response, persons, time, record_id))
            conn.commit()
            flash('Record updated successfully!', 'success')
            return redirect(url_for('admin'))
        except Exception as e:
            flash(f'Error updating record: {e}', 'danger')
            return redirect(url_for('admin'))

    # Fetch the record for editing
    record = conn.execute("SELECT * FROM bot_responses WHERE id = ?", (record_id,)).fetchone()
    conn.close()

    if record:
        return render_template('edit_record.html', record=record)
    else:
        flash('Record not found.', 'danger')
        return redirect(url_for('admin'))


# Route: Delete Record
@app.route('/delete_record/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    if 'user_id' not in session:
        flash('You need to log in to access this page.', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()

    try:
        conn.execute("DELETE FROM bot_responses WHERE id = ?", (record_id,))
        conn.commit()
        flash('Record deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting record: {e}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('admin'))


# Route for chatbot API
@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '').strip().lower()
    print(f"Received message: {user_message}")

    matched_query, responses = query_response(user_message)

    if responses:
        if matched_query.lower().startswith("how to get"):
            prefix = "To get the"
        elif matched_query.lower().startswith("how to use"):
            prefix = "To use the"
        else:
            prefix = "For"

        reply = f"<b>{matched_query.split('?')[0]}:</b><br><br>"
        for index, row in enumerate(responses):
            step = f"{row[0]}<br>Accountable Person: {row[1]}<br>Time: {row[2]}<br><br>"
            reply += step

        reply += "<b>END OF TRANSACTION</b>"
    else:
        reply = "Sorry, I didn't understand that. Please ask about Barangay Local Government Unit services."

    return jsonify({'reply': reply})

# Route: Logout
@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Remove user_id from session
    session.pop('user_name', None)  # Remove user_name from session
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))

# Main
if __name__ == '__main__':
    app.run(debug=True)
