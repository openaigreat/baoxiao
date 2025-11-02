from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import get_db

bp = Blueprint('todos', __name__)

@bp.route('/todos', methods=['GET', 'POST'])
def todos():
    """显示所有todo或添加新todo"""
    conn = get_db()
    
    if request.method == 'POST':
        # 添加新todo
        content = request.form.get('content')
        
        if not content:
            flash('请输入待办内容')
        else:
            try:
                # 设置默认project_id为1，或根据实际需求设置
                project_id = 1  # 可以根据需要修改为其他默认值或查询第一个项目的ID
                # 获取当前最小的sort_order值，用于新添加的todo（新任务排在最上面）
                min_order = conn.execute('SELECT MIN(sort_order) FROM todos').fetchone()[0]
                # 如果没有记录，从0开始；否则使用比最小值更小的值
                new_order = (min_order - 1) if min_order is not None else 0
                conn.execute(
                    'INSERT INTO todos (project_id, content, sort_order) VALUES (?, ?, ?)',
                    (project_id, content, new_order)
                )
                conn.commit()
                flash('待办事项添加成功')
            except Exception as e:
                flash(f'添加待办事项失败: {str(e)}')
        
        return redirect(url_for('todos.todos'))
    
    # 获取所有todo，不按项目分组
    todos = conn.execute(
        'SELECT id, content, completed, created_at, completed_at, sort_order FROM todos ORDER BY completed ASC, CASE WHEN completed = 0 THEN sort_order ELSE 9999 END ASC'
    ).fetchall()
    
    conn.close()
    
    return render_template('todos.html', todos=todos)

@bp.route('/toggle_todo/<int:todo_id>', methods=['POST'])
def toggle_todo(todo_id):
    """切换todo的完成状态 - 总是返回JSON响应，不进行任何重定向"""
    conn = get_db()
    try:
        # 从表单中获取completed参数（确保正确处理前端发送的值）
        completed_param = request.form.get('completed')
        
        # 明确转换参数值
        new_status = 1 if completed_param == '1' else 0
        
        # 更新数据库
        if new_status == 1:  # 标记为完成
            conn.execute(
                'UPDATE todos SET completed = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?', 
                (new_status, todo_id)
            )
        else:  # 标记为未完成，清空完成时间
            conn.execute(
                'UPDATE todos SET completed = ?, completed_at = NULL WHERE id = ?', 
                (new_status, todo_id)
            )
        conn.commit()
        
        # 返回标准格式的JSON响应
        return jsonify({
            'success': True,
            'id': todo_id,
            'completed': bool(new_status)
        }), 200
    except Exception as e:
        # 错误情况下返回JSON
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

@bp.route('/update_todo_order', methods=['POST'])
def update_todo_order():
    """更新todo的排序"""
    conn = get_db()
    try:
        # 获取排序数据
        data = request.get_json()
        todo_ids = data.get('todoIds', [])
        
        # 确保todo_ids是整数列表
        todo_ids = [int(todo_id) for todo_id in todo_ids]
        
        if not todo_ids:
            return jsonify({'success': False, 'error': '没有收到排序数据'}), 400
        
        # 开始事务
        conn.execute('BEGIN TRANSACTION')
        
        # 更新每个todo的排序
        updated_count = 0
        for order, todo_id in enumerate(todo_ids):
            # 确保order是整数类型
            int_order = int(order)
            int_todo_id = int(todo_id)
            
            result = conn.execute(
                'UPDATE todos SET sort_order = ? WHERE id = ?',
                (int_order, int_todo_id)
            )
            updated_count += result.rowcount
        
        # 提交事务
        conn.commit()
        
        # 验证更新是否成功 - 查询更新后的排序
        if todo_ids:
            # 为每个ID创建一个占位符
            placeholders = ','.join(['?'] * len(todo_ids))
            # 直接使用todo_ids作为参数，确保类型正确
            updated_todos = conn.execute(
                f'SELECT id, sort_order FROM todos WHERE id IN ({placeholders}) ORDER BY sort_order',
                todo_ids
            ).fetchall()
        else:
            updated_todos = []
        
        # 构建验证数据
        verification_data = []
        for t in updated_todos:
            verification_data.append({
                'id': t['id'], 
                'sort_order': t['sort_order']
            })
        
        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'todo_ids_received': len(todo_ids),
            'verification': verification_data
        })
    except Exception as e:
        # 发生错误时回滚事务
        try:
            conn.rollback()
        except:
            pass
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@bp.route('/project_todos/<int:project_id>', methods=['GET', 'POST'])
def project_todos(project_id):
    """显示特定项目的todo"""
    conn = get_db()
    
    # 获取项目信息
    project = conn.execute('SELECT id, name FROM projects WHERE id = ?', (project_id,)).fetchone()
    if not project:
        flash('项目不存在')
        return redirect(url_for('todos.todos'))
    
    if request.method == 'POST':
        # 添加新todo
        content = request.form.get('content')
        
        if not content:
            flash('请输入待办内容')
        else:
            try:
                # 获取当前最小的sort_order值，用于新添加的todo（新任务排在最上面）
                min_order = conn.execute('SELECT MIN(sort_order) FROM todos WHERE project_id = ?', (project_id,)).fetchone()[0]
                # 如果没有记录，从0开始；否则使用比最小值更小的值
                new_order = (min_order - 1) if min_order is not None else 0
                conn.execute(
                    'INSERT INTO todos (project_id, content, sort_order) VALUES (?, ?, ?)',
                    (project_id, content, new_order)
                )
                conn.commit()
                flash('待办事项添加成功')
            except Exception as e:
                flash(f'添加待办事项失败: {str(e)}')
        
        return redirect(url_for('todos.project_todos', project_id=project_id))
    
    # 获取该项目的所有todo
    todos = conn.execute(
        'SELECT id, content, completed, created_at, completed_at, sort_order FROM todos WHERE project_id = ? ORDER BY completed ASC, CASE WHEN completed = 0 THEN sort_order ELSE 9999 END ASC',
        (project_id,)
    ).fetchall()
    
    conn.close()
    
    return render_template('project_todos.html', project=project, todos=todos)