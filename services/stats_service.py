from models import get_db
import logging
from services.exceptions import DatabaseError

class StatsService:
    def __init__(self):
        pass
    
    def get_project_stats(self):
        """
        获取项目统计信息（只显示进行中的项目）
        :return: 项目统计列表
        """
        conn = get_db()
        try:
            # 获取项目统计，包括支出总额、已提交金额和回款状态统计（只显示进行中的项目）
            project_stats = conn.execute('''
                SELECT p.id, p.name,
                       COALESCE(SUM(e.amount), 0) AS total_expense,
                       COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL THEN e.amount ELSE 0 END), 0) AS submitted_amount,
                       COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status = '已回款' THEN e.amount ELSE 0 END), 0) AS paid_amount,
                       COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status != '已回款' THEN e.amount ELSE 0 END), 0) AS unpaid_amount,
                       p.note, p.status
                FROM projects p
                LEFT JOIN expenses e ON p.id = e.project_id
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
                WHERE p.status = '进行中'
                GROUP BY p.id, p.name, p.note, p.status
            ''').fetchall()
            
            # 获取无项目支出统计，包括已提交金额和回款状态统计
            orphan_stats = conn.execute('''
                SELECT COALESCE(SUM(e.amount), 0) AS total_expense,
                       COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL THEN e.amount ELSE 0 END), 0) AS submitted_amount,
                       COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status = '已回款' THEN e.amount ELSE 0 END), 0) AS paid_amount,
                       COALESCE(SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status != '已回款' THEN e.amount ELSE 0 END), 0) AS unpaid_amount
                FROM expenses e
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
                WHERE e.project_id IS NULL
            ''').fetchone()
            
            orphan_total = orphan_stats['total_expense'] or 0
            orphan_submitted = orphan_stats['submitted_amount'] or 0
            orphan_paid = orphan_stats['paid_amount'] or 0
            orphan_unpaid = orphan_stats['unpaid_amount'] or 0
            
            # 初始化统计结果列表
            stats = []
            
            # 如果有无项目支出，将其添加到统计结果的最前面
            if orphan_total > 0:
                # 使用字典模拟Row对象来显示无项目支出
                orphan_record = {'id': None, 'name': '无项目支出', 'project_amount': 0, 
                                'total_expense': orphan_total, 'submitted_amount': orphan_submitted,
                                'paid_amount': orphan_paid, 'unpaid_amount': orphan_unpaid, 'note': '', 'status': '进行中'}
                stats.append(orphan_record)
            
            # 添加正常项目统计，并处理None值
            for project in project_stats:
                # 转换Row对象为字典，并处理None值
                project_dict = dict(project)
                # 设置默认的项目预算金额为0
                project_dict['project_amount'] = 0
                project_dict['total_expense'] = project_dict.get('total_expense', 0) or 0
                project_dict['submitted_amount'] = project_dict.get('submitted_amount', 0) or 0
                project_dict['paid_amount'] = project_dict.get('paid_amount', 0) or 0
                project_dict['unpaid_amount'] = project_dict.get('unpaid_amount', 0) or 0
                stats.append(project_dict)
                
            return stats
        except Exception as e:
            logging.error(f"Error getting project stats: {e}")
            raise DatabaseError("获取项目统计数据失败")
        finally:
            conn.close()
    
    def get_expenses_by_project(self, project_id, sort_by='category', sort_order='asc'):
        """
        根据项目ID获取支出明细
        :param project_id: 项目ID
        :param sort_by: 排序字段
        :param sort_order: 排序顺序
        :return: 支出明细列表
        """
        # 验证排序字段
        valid_sort_fields = ['category', 'date', 'description', 'amount', 'payment_method']
        # 保存原始排序字段用于模板显示
        original_sort_by = sort_by
        # 允许使用'purpose'作为排序字段（内部会映射到'description'）
        if sort_by == 'purpose':
            sort_by = 'description'
        # 允许使用'note'作为排序字段（内部会映射到'payment_method'）
        elif sort_by == 'note':
            sort_by = 'payment_method'
        elif sort_by not in valid_sort_fields:
            sort_by = 'category'
            original_sort_by = 'category'
        
        # 验证排序顺序
        if sort_order not in ['asc', 'desc']:
            sort_order = 'asc'
            
        conn = get_db()
        try:
            # 构建动态排序查询
            where_clause = 'WHERE e.project_id = ?' if project_id is not None else 'WHERE e.project_id IS NULL'
            
            # 处理特殊排序规则 - 对于类别排序，始终让"其他"排在前面
            if sort_by == 'category':
                order_expression = f'''
                    CASE 
                        WHEN e.category = '其他' THEN 0 
                        ELSE 1 
                    END, 
                    e.category {sort_order}
                '''
            else:
                order_expression = f'{sort_by} {sort_order}'
            
            query = f'''
                SELECT e.id, e.date, e.category, e.amount, e.description as purpose, e.project_id, 
                       e.created_at, e.created_by, p.name as project_name, 
                       CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status,
                       e.payment_method as note
                FROM expenses e
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                {where_clause} AND re.expense_id IS NULL
                ORDER BY {order_expression}
            '''
            
            expenses = conn.execute(query, (project_id,) if project_id is not None else ()).fetchall()
            
            # 获取总金额
            total_query = '''
                SELECT SUM(amount) as total
                FROM expenses e
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                WHERE e.project_id ''' + ('= ?' if project_id is not None else 'IS NULL') + ''' AND re.expense_id IS NULL'''
            total_amount = conn.execute(total_query, (project_id,) if project_id is not None else ()).fetchone()['total'] or 0
            
            # 获取所有进行中的项目列表，用于批量修改
            projects = conn.execute('''
                SELECT id, name
                FROM projects
                WHERE status = ?
                ORDER BY name
            ''', ('进行中',)).fetchall()
            
            return {
                'expenses': expenses,
                'total_amount': total_amount,
                'projects': projects,
                'current_sort': sort_by,
                'current_order': sort_order,
                'next_sort_order': 'desc' if sort_order == 'asc' else 'asc'
            }
        except Exception as e:
            logging.error(f"Error getting expenses by project: {e}")
            raise DatabaseError("获取项目支出明细失败")
        finally:
            conn.close()
    
    def get_category_stats(self, session):
        """
        获取费用分类统计
        :param session: Flask会话对象
        :return: 分类统计列表
        """
        conn = get_db()
        try:
            # 获取所有费用类别及其统计信息
            categories = conn.execute('''
                SELECT category, 
                       COUNT(*) as expense_count,
                       SUM(amount) as total_amount,
                       COUNT(CASE WHEN re.expense_id IS NOT NULL THEN 1 END) as submitted_count,
                       SUM(CASE WHEN re.expense_id IS NOT NULL THEN amount ELSE 0 END) as submitted_amount
                FROM expenses e
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                WHERE e.created_by = ?
                GROUP BY category
                ORDER BY total_amount DESC
            ''', (session.get('user_id', 1),)).fetchall()
            
            # 计算总计
            total_stats = conn.execute('''
                SELECT COUNT(*) as total_count,
                       SUM(amount) as total_amount,
                       COUNT(CASE WHEN re.expense_id IS NOT NULL THEN 1 END) as total_submitted_count,
                       SUM(CASE WHEN re.expense_id IS NOT NULL THEN amount ELSE 0 END) as total_submitted_amount
                FROM expenses e
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                WHERE e.created_by = ?
            ''', (session.get('user_id', 1),)).fetchone()
            
            return {
                'categories': categories,
                'total_stats': total_stats
            }
        except Exception as e:
            logging.error(f"Error getting category stats: {e}")
            raise DatabaseError("获取费用分类统计失败")
        finally:
            conn.close()
    
    def get_expenses_by_category(self, category_name, session, sort_by='project_name', sort_order='asc'):
        """
        根据费用分类获取支出明细
        :param category_name: 费用分类名称
        :param session: Flask会话对象
        :param sort_by: 排序字段
        :param sort_order: 排序顺序
        :return: 支出明细列表和相关信息
        """
        # 验证排序参数
        valid_sort_fields = ['project_name', 'date', 'category', 'purpose', 'amount', 'note', 'payment_method']
        if sort_by not in valid_sort_fields:
            sort_by = 'project_name'
        
        if sort_order not in ['asc', 'desc']:
            sort_order = 'asc'
            
        conn = get_db()
        try:
            # 获取该类别的所有费用记录，支持动态排序，并左连接报销表以获取报销状态
            # 根据expenses.py中的实现，description字段存储purpose内容，payment_method字段存储note内容
            query = f'''
                SELECT e.id, e.date, e.category, e.amount, e.description as purpose, e.project_id, 
                       e.created_at, e.created_by, p.name as project_name, 
                       CASE WHEN re.expense_id IS NOT NULL THEN 1 ELSE 0 END as reimbursement_status,
                       e.payment_method as note
                FROM expenses e
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                WHERE e.created_by = ? AND e.category = ? AND re.expense_id IS NULL
                ORDER BY {sort_by} {sort_order}
            '''
            params = (session.get('user_id', 1), category_name)
            
            expenses = conn.execute(query, params).fetchall()
            
            # 获取总金额
            total_amount = conn.execute('''
                SELECT SUM(amount) as total
                FROM expenses e
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                WHERE e.created_by = ? AND e.category = ? AND re.expense_id IS NULL
            ''', (session.get('user_id', 1), category_name)).fetchone()['total'] or 0
            
            # 获取所有进行中的项目列表，用于批量修改
            projects = conn.execute('''
                SELECT id, name
                FROM projects
                WHERE status = ?
                ORDER BY name
            ''', ('进行中',)).fetchall()
            
            return {
                'expenses': expenses,
                'total_amount': total_amount,
                'projects': projects,
                'current_sort': sort_by,
                'current_order': sort_order,
                'next_sort_order': 'desc' if sort_order == 'asc' else 'asc'
            }
        except Exception as e:
            logging.error(f"Error getting expenses by category: {e}")
            raise DatabaseError("获取分类支出明细失败")
        finally:
            conn.close()
    
    def get_expense_payment_status(self, filters=None):
        """
        获取支出记录的回款状态
        :param filters: 筛选条件字典，可包含project_name, category, payment_status, sort_by等
        :return: 支出记录及其回款状态列表
        """
        conn = get_db()
        try:
            # 构建查询条件
            where_conditions = []
            params = []
            
            if filters:
                # 项目名称筛选
                if filters.get('project_name'):
                    where_conditions.append("p.name LIKE ?")
                    params.append(f"%{filters['project_name']}%")
                
                # 费用类别筛选
                if filters.get('category'):
                    where_conditions.append("e.category LIKE ?")
                    params.append(f"%{filters['category']}%")
                
                # 回款状态筛选
                if filters.get('payment_status'):
                    payment_status = filters['payment_status']
                    if payment_status == '未报销':
                        where_conditions.append("re.expense_id IS NULL")
                    elif payment_status == '已报销未回款':
                        where_conditions.append("re.expense_id IS NOT NULL AND r.status IN ('已提交', '审核中', '已批准')")
                    elif payment_status == '已回款':
                        where_conditions.append("r.status = '已回款'")
            
            # 构建WHERE子句
            where_clause = ""
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)
            
            # 构建ORDER BY子句
            order_clause = "e.date DESC, e.id DESC"  # 默认排序
            if filters and filters.get('sort_by'):
                sort_by = filters['sort_by']
                if sort_by == 'date_asc':
                    order_clause = "e.date ASC, e.id ASC"
                elif sort_by == 'amount_desc':
                    order_clause = "e.amount DESC, e.date DESC"
                elif sort_by == 'amount_asc':
                    order_clause = "e.amount ASC, e.date DESC"
            
            # 获取所有支出记录及其回款状态
            query = f'''
                SELECT 
                    e.id as expense_id,
                    e.date as expense_date,
                    e.category,
                    e.description as purpose,
                    e.amount as expense_amount,
                    e.project_id,
                    p.name as project_name,
                    re.reimbursement_id,
                    r.status as reimbursement_status,
                    r.total_amount as reimbursement_total,
                    r.total_paid as reimbursement_paid,
                    CASE 
                        WHEN re.expense_id IS NULL THEN '未报销'
                        WHEN r.status = '已回款' THEN '已回款'
                        WHEN r.status IN ('已提交', '审核中', '已批准') THEN '已报销未回款'
                        ELSE '未报销'
                    END as payment_status,
                    CASE 
                        WHEN re.expense_id IS NOT NULL AND r.total_amount > 0 THEN
                            (e.amount / r.total_amount) * r.total_paid
                        ELSE 0
                    END as allocated_paid_amount
                FROM expenses e
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
                {where_clause}
                ORDER BY {order_clause}
            '''
            
            expenses = conn.execute(query, params).fetchall()
            
            return expenses
        except Exception as e:
            logging.error(f"Error getting expense payment status: {e}")
            raise DatabaseError("获取支出回款状态失败")
        finally:
            conn.close()

    def get_project_payment_stats(self, page=1, per_page=10):
        """
        按项目统计回款情况（支持分页）
        :param page: 页码，默认为1
        :param per_page: 每页记录数，默认为10
        :return: 项目回款统计列表和分页信息
        """
        conn = get_db()
        try:
            # 计算偏移量
            offset = (page - 1) * per_page
            
            # 获取总记录数
            count_query = '''
                SELECT COUNT(DISTINCT COALESCE(p.id, 0)) as count
                FROM expenses e
                LEFT JOIN projects p ON e.project_id = p.id
            '''
            total_result = conn.execute(count_query).fetchone()
            total_count = total_result['count']
            total_pages = (total_count + per_page - 1) // per_page
            
            # 按项目统计各类支出金额（分页）
            stats_query = '''
                SELECT 
                    COALESCE(p.id, 0) as project_id,
                    COALESCE(p.name, '无项目') as project_name,
                    SUM(CASE WHEN re.expense_id IS NULL THEN e.amount ELSE 0 END) as unreimbursed_amount,
                    SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status != '已回款' THEN e.amount ELSE 0 END) as reimbursed_unpaid_amount,
                    SUM(CASE WHEN re.expense_id IS NOT NULL AND r.status = '已回款' THEN e.amount ELSE 0 END) as reimbursed_paid_amount,
                    COUNT(CASE WHEN re.expense_id IS NULL THEN 1 END) as unreimbursed_count,
                    COUNT(CASE WHEN re.expense_id IS NOT NULL AND r.status != '已回款' THEN 1 END) as reimbursed_unpaid_count,
                    COUNT(CASE WHEN re.expense_id IS NOT NULL AND r.status = '已回款' THEN 1 END) as reimbursed_paid_count
                FROM expenses e
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
                GROUP BY p.id, p.name
                ORDER BY p.name
                LIMIT ? OFFSET ?
            '''
            stats = conn.execute(stats_query, (per_page, offset)).fetchall()
            
            return {
                'stats': stats,
                'total_count': total_count,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            }
        except Exception as e:
            logging.error(f"Error getting project payment stats: {e}")
            raise DatabaseError("获取项目回款统计失败")
        finally:
            conn.close()

    def get_expenses_by_payment_status(self, project_id, status):
        """
        根据项目ID和回款状态获取支出记录
        :param project_id: 项目ID，None表示所有项目，0表示无项目
        :param status: 回款状态 (unreimbursed, reimbursed_unpaid, reimbursed_paid)
        :return: 支出记录列表
        """
        conn = get_db()
        try:
            # 构建基础查询
            base_query = '''
                SELECT 
                    e.id as expense_id,
                    e.date as expense_date,
                    e.category,
                    e.description as purpose,
                    e.amount as expense_amount,
                    e.project_id,
                    p.name as project_name,
                    re.reimbursement_id,
                    r.status as reimbursement_status,
                    r.total_amount as reimbursement_total,
                    r.total_paid as reimbursement_paid
                FROM expenses e
                LEFT JOIN projects p ON e.project_id = p.id
                LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
            '''
            
            # 构建WHERE条件
            conditions = []
            params = []
            
            # 项目条件
            if project_id is not None:
                if project_id == 0:  # 无项目
                    conditions.append('e.project_id IS NULL')
                else:  # 特定项目
                    conditions.append('e.project_id = ?')
                    params.append(project_id)
            
            # 状态条件
            if status == 'unreimbursed':
                conditions.append('re.expense_id IS NULL')
            elif status == 'reimbursed_unpaid':
                conditions.append('re.expense_id IS NOT NULL AND r.status != "已回款"')
            elif status == 'reimbursed_paid':
                conditions.append('re.expense_id IS NOT NULL AND r.status = "已回款"')
            
            # 组合查询
            if conditions:
                query = base_query + ' WHERE ' + ' AND '.join(conditions)
            else:
                query = base_query
                
            query += ' ORDER BY e.date DESC, e.id DESC'
            
            expenses = conn.execute(query, params).fetchall()
            return expenses
        except Exception as e:
            logging.error(f"Error getting expenses by payment status: {e}")
            raise DatabaseError("获取支出记录失败")
        finally:
            conn.close()

    def get_all_expenses_by_project(self, project_id, page=1, per_page=10):
        """
        获取指定项目的所有支出记录（支持分页）
        :param project_id: 项目ID，0表示无项目
        :param page: 页码，默认为1
        :param per_page: 每页记录数，默认为10
        :return: 支出记录列表和分页信息
        """
        conn = get_db()
        try:
            # 计算偏移量
            offset = (page - 1) * per_page
            
            # 获取总记录数
            if project_id == 0:  # 无项目
                count_query = '''
                    SELECT COUNT(*) as count
                    FROM expenses e
                    WHERE e.project_id IS NULL
                '''
                total_result = conn.execute(count_query).fetchone()
            else:  # 特定项目
                count_query = '''
                    SELECT COUNT(*) as count
                    FROM expenses e
                    WHERE e.project_id = ?
                '''
                total_result = conn.execute(count_query, (project_id,)).fetchone()
            
            total_count = total_result['count']
            total_pages = (total_count + per_page - 1) // per_page
            
            # 构建查询
            if project_id == 0:  # 无项目
                query = '''
                    SELECT 
                        e.id as expense_id,
                        e.date as expense_date,
                        e.category,
                        e.description as purpose,
                        e.amount as expense_amount,
                        e.project_id,
                        p.name as project_name,
                        re.reimbursement_id,
                        r.status as reimbursement_status,
                        r.total_amount as reimbursement_total,
                        r.total_paid as reimbursement_paid
                    FROM expenses e
                    LEFT JOIN projects p ON e.project_id = p.id
                    LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                    LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
                    WHERE e.project_id IS NULL
                    ORDER BY e.date DESC, e.id DESC
                    LIMIT ? OFFSET ?
                '''
                expenses = conn.execute(query, (per_page, offset)).fetchall()
            else:  # 特定项目
                query = '''
                    SELECT 
                        e.id as expense_id,
                        e.date as expense_date,
                        e.category,
                        e.description as purpose,
                        e.amount as expense_amount,
                        e.project_id,
                        p.name as project_name,
                        re.reimbursement_id,
                        r.status as reimbursement_status,
                        r.total_amount as reimbursement_total,
                        r.total_paid as reimbursement_paid
                    FROM expenses e
                    LEFT JOIN projects p ON e.project_id = p.id
                    LEFT JOIN reimbursement_expenses re ON e.id = re.expense_id
                    LEFT JOIN reimbursements r ON re.reimbursement_id = r.id
                    WHERE e.project_id = ?
                    ORDER BY e.date DESC, e.id DESC
                    LIMIT ? OFFSET ?
                '''
                expenses = conn.execute(query, (project_id, per_page, offset)).fetchall()
            
            return {
                'expenses': expenses,
                'total_count': total_count,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            }
        except Exception as e:
            logging.error(f"Error getting all expenses by project: {e}")
            raise DatabaseError("获取项目支出记录失败")
        finally:
            conn.close()
