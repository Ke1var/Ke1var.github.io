from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import case
from collections import defaultdict

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///projectsite.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here' 

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'loging'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(50), nullable=False)
    text = db.Column(db.Text(400), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    due_date = db.Column(db.DateTime)
    task_type = db.Column(db.String(20), default='daily')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


@app.route('/reg', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            return 'Пользователь уже существует'
        
        user = User(username=username)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect('/tasks')
    
    return render_template('reg.html')

@app.route('/loging', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect('/tasks')
        else:
            return 'Неверное имя пользователя или пароль'
    
    return render_template('loging.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')


@app.route("/")
@app.route("/main")
def index():
    return render_template('index.html')

@app.route("/about")
def about():
    return render_template('about.html')

@app.route("/settings")
@login_required
def settings():
    return render_template('settings.html')

@app.route("/analytics")
@login_required
def analytics():
    return redirect(url_for('analytics_week'))


@app.route("/analytics/week")
@login_required
def analytics_week():
    today = datetime.today().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    period_label = f"Неделя: {start_of_week.strftime('%d.%m')} – {end_of_week.strftime('%d.%m')}"
    tasks_in_period = Post.query.filter(
        Post.user_id == current_user.id,
        db.func.date(Post.due_date) >= start_of_week,
        db.func.date(Post.due_date) <= end_of_week
    ).all()

    chart_data = prepare_chart_data(tasks_in_period, start_of_week, end_of_week)
    stats = calculate_stats(tasks_in_period)

    return render_template(
        'analytics.html',
        chart_data=chart_data,
        stats=stats,
        period_label=period_label,
        active_tab='week'
    )


@app.route("/analytics/month")
@login_required
def analytics_month():
    today = datetime.today().date()
    start_of_month = today.replace(day=1)
    if today.month == 12:
        end_of_month = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    period_label = f"Месяц: {start_of_month.strftime('%B %Y')}"
    tasks_in_period = Post.query.filter(
        Post.user_id == current_user.id,
        db.func.date(Post.due_date) >= start_of_month,
        db.func.date(Post.due_date) <= end_of_month
    ).all()

    chart_data = prepare_chart_data(tasks_in_period, start_of_month, end_of_month)
    stats = calculate_stats(tasks_in_period)

    return render_template(
        'analytics.html',
        chart_data=chart_data,
        stats=stats,
        period_label=period_label,
        active_tab='month'
    )


def prepare_chart_data(tasks, start_date, end_date):
    now = datetime.now()
    
    date_range = []
    current = start_date
    while current <= end_date:
        date_range.append(current)
        current += timedelta(days=1)

    daily_data = {d: {'completed_on_time': 0, 'completed_late': 0, 'missed': 0, 'pending': 0} for d in date_range}

    for task in tasks:
        if not task.due_date:
            continue
        task_date = task.due_date.date()
        if task_date not in daily_data:
            continue

        if task.completed:
            if task.completed_at and task.completed_at <= task.due_date:
                daily_data[task_date]['completed_on_time'] += 1
            else:
                daily_data[task_date]['completed_late'] += 1
        else:
            if task.due_date < now:
                daily_data[task_date]['missed'] += 1
            else:
                daily_data[task_date]['pending'] += 1

    labels = [d.strftime('%d.%m') for d in date_range]
    completed_on_time = [daily_data[d]['completed_on_time'] for d in date_range]
    completed_late = [daily_data[d]['completed_late'] for d in date_range]
    missed = [daily_data[d]['missed'] for d in date_range]
    pending = [daily_data[d]['pending'] for d in date_range]

    return {
        'labels': labels,
        'datasets': [
            {'label': 'Выполнено вовремя', 'data': completed_on_time, 'backgroundColor': '#28a745'},
            {'label': 'Выполнено не вовремя', 'data': completed_late, 'backgroundColor': '#ffc107'},
            {'label': 'Пропущенные', 'data': missed, 'backgroundColor': '#dc3545'},
            {'label': 'Можно выполнить вовремя', 'data': pending, 'backgroundColor': '#17a2b8'}
        ]
    }


def calculate_stats(tasks):
    now = datetime.now()
    completed_on_time = 0
    completed_late = 0
    missed = 0
    pending = 0

    for task in tasks:
        if task.completed:
            if task.completed_at and task.completed_at <= task.due_date:
                completed_on_time += 1
            else:
                completed_late += 1
        else:
            if task.due_date and task.due_date < now:
                missed += 1
            else:
                pending += 1

    return {
        'completed_on_time': completed_on_time,
        'completed_late': completed_late,
        'missed': missed,
        'pending': pending,
        'total_completed': completed_on_time + completed_late,
        'total_uncompleted': missed + pending
    }

@app.route("/support")
def support():
    return render_template('support.html')

@app.route("/create", methods=['POST', 'GET'])
@login_required
def create():
    if request.method == 'POST':
        title = request.form['title']
        text = request.form['text']
        due_date_str = request.form.get('due_date')
        task_type = request.form.get('task_type', 'daily')
        
        due_date = None
        if due_date_str:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
        
        post = Post(title=title, text=text, user_id=current_user.id, due_date=due_date, task_type=task_type)

        try:
            db.session.add(post)
            db.session.commit()
            return redirect('/tasks')
        except Exception as e:
            print(f"Ошибка при добавлении задачи: {e}")
            return 'При добавлении задачи произошла ошибка'
    else:
        return render_template('create.html')

@app.route("/tasks")
@login_required
def tasks():
    all_tasks = Post.query.filter_by(user_id=current_user.id)\
        .order_by(
            Post.completed.asc(),
            case(
                (Post.task_type == 'important', 0),
                (Post.task_type == 'daily', 1),
                else_=2
            ).asc(),
            Post.due_date.asc()
        )\
        .all()
    return render_template('tasks.html', tasks=all_tasks, now=datetime.now)

@app.route("/tasks/important")
@login_required
def important_tasks():
    important_tasks = Post.query.filter_by(user_id=current_user.id, task_type='important')\
        .order_by(Post.completed.asc(), Post.due_date.asc())\
        .all()
    return render_template('tasks.html', tasks=important_tasks, now=datetime.now, active_tab='important')

@app.route("/tasks/daily")
@login_required
def daily_tasks():
    daily_tasks = Post.query.filter_by(user_id=current_user.id, task_type='daily')\
        .order_by(Post.completed.asc(), Post.due_date.asc())\
        .all()
    return render_template('tasks.html', tasks=daily_tasks, now=datetime.now, active_tab='daily')

@app.route("/delete/<int:id>")
@login_required
def delete(id):
    
    task = Post.query.filter_by(id=id, user_id=current_user.id).first()
    
    if not task:
        return 'Задача не найдена или у вас нет прав для ее удаления'
    
    try:
        db.session.delete(task)
        db.session.commit()
        return redirect('/tasks')
    except:
        return 'При удалении задачи произошла ошибка'

@app.route("/reg")
def reg():
    return render_template('reg.html')

@app.route("/loging")
def loging():
    return render_template('loging.html')


@app.route("/complete/<int:id>")
@login_required
def complete(id):
    task = Post.query.filter_by(id=id, user_id=current_user.id).first()
    
    if not task:
        return 'Задача не найдена'
    
    try:
        task.completed = True
        task.completed_at = datetime.now()
        db.session.commit()
        return redirect('/tasks')
    except Exception as e:
        print(f"Ошибка: {e}")
        return 'При обновлении задачи произошла ошибка'

@app.route("/uncomplete/<int:id>")
@login_required
def uncomplete(id):
    task = Post.query.filter_by(id=id, user_id=current_user.id).first()
    
    if not task:
        return 'Задача не найдена'
    
    try:
        task.completed = False
        task.completed_at = None
        db.session.commit()
        return redirect('/tasks')
    except:
        return 'При обновлении задачи произошла ошибка'

if __name__ == "__main__":
    app.run(debug=True)