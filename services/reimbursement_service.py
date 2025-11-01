class DatabaseError(Exception):
    """数据库操作相关异常"""
    pass

class ValidationError(Exception):
    """数据验证相关异常"""
    pass
import sqlite3
from datetime import datetime
import logging
from models import get_db
from .exceptions import DatabaseError, ValidationError

class ReimbursementService:
    def __init__(self):
        pass
    
    def get_draft_and_rejected_reimbursements(self):
        """获取草稿或已拒绝状态的报销单列表"""
        conn = get_db()
        try:
            reimbursements = conn.execute('''
                SELECT r.*,
                       (SELECT COUNT(*) FROM reimbursement_expenses WHERE reimbursement_id = r.id) as expense_count,
                       COALESCE((SELECT SUM(reimbursement_amount) FROM reimbursement_expenses WHERE reimbursement_id = r.id), 0) as calculated_total
                FROM reimbursements r
                WHERE r.status IN ('草稿', '已拒绝')
                ORDER BY r.created_at DESC
            ''').fetchall()
            
            result = []
            for r in reimbursements:
                result.append({
                    'id': r['id'],
                    'submission_date': r['submit_date'],
                    'total_amount': r['calculated_total'] or 0,
                    'status': r['status']
                })
            
            return result
        except sqlite3.Error as e:
            logging.error(f"Database error in get_draft_and_rejected_reimbursements: {e}")
            raise DatabaseError("获取报销单列表失败")
        except Exception as e:
            logging.error(f"Error in get_draft_and_rejected_reimbursements: {e}")
            raise DatabaseError("获取报销单列表时发生未知错误")
        finally:
            conn.close()
    
    def get_reimbursement_payments(self, reimbursement_id):
        """获取报销单的回款记录"""
        if not reimbursement_id:
            raise ValidationError("报销单ID不能为空")
            
        conn = get_db()
        try:
            payments = conn.execute('''
                SELECT * FROM reimbursement_payments 
                WHERE reimbursement_id = ? 
                ORDER BY payment_date DESC
            ''', (reimbursement_id,)).fetchall()
            return payments
        except sqlite3.Error as e:
            logging.error(f"Database error in get_reimbursement_payments: {e}")
            raise DatabaseError("获取回款记录失败")
        except Exception as e:
            logging.error(f"Error in get_reimbursement_payments: {e}")
            raise DatabaseError("获取回款记录时发生未知错误")
        finally:
            conn.close()
    
    def add_expense_to_reimbursement(self, reimbursement_id, expense_id, reimbursement_amount, session):
        """添加支出到报销单"""
        # 参数验证
        if not reimbursement_id:
            return {'success': False, 'error': '报销单ID不能为空'}
        
        if not expense_id:
            return {'success': False, 'error': '支出记录ID不能为空'}
            
        if reimbursement_amount is None or reimbursement_amount <= 0:
            return {'success': False, 'error': '报销金额必须大于0'}
        
        conn = get_db()
        try:
            # 验证报销单是否存在且状态允许编辑
            reimbursement = conn.execute('''
                SELECT * FROM reimbursements WHERE id = ?
            ''', (reimbursement_id,)).fetchone()
            
            if not reimbursement:
                return {'success': False, 'error': '报销单不存在'}
            
            if reimbursement['status'] not in ['草稿', '已拒绝']:
                return {'success': False, 'error': '只有草稿或已拒绝状态的报销单可以添加支出记录'}
            
            # 验证支出记录是否存在
            expense = conn.execute('''
                SELECT * FROM expenses WHERE id = ?
            ''', (expense_id,)).fetchone()
            
            if not expense:
                return {'success': False, 'error': '支出记录不存在'}
            
            # 检查支出记录是否已关联到其他报销单
            existing = conn.execute('''
                SELECT 1 FROM reimbursement_expenses WHERE expense_id = ?
            ''', (expense_id,)).fetchone()
            
            if existing:
                return {'success': False, 'error': '该支出记录已关联到其他报销单'}
            
            # 添加关联
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('''
                INSERT INTO reimbursement_expenses (reimbursement_id, expense_id, reimbursement_amount, added_date)
                VALUES (?, ?, ?, ?)
            ''', (reimbursement_id, expense_id, reimbursement_amount, current_time))
            
            conn.commit()
            return {'success': True}
        except sqlite3.Error as e:
            conn.rollback()
            logging.error(f"Database error in add_expense_to_reimbursement: {e}")
            return {'success': False, 'error': '数据库操作失败'}
        except Exception as e:
            conn.rollback()
            logging.error(f"Error in add_expense_to_reimbursement: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()
    
    def add_multiple_expenses_to_reimbursement(self, reimbursement_id, expense_ids, session):
        """批量添加支出到报销单"""
        # 参数验证
        if not reimbursement_id:
            return {'success': False, 'error': '报销单ID不能为空'}
        
        if not expense_ids:
            return {'success': False, 'error': '支出记录ID列表不能为空'}
            
        conn = get_db()
        try:
            # 验证报销单是否存在且状态允许编辑
            reimbursement = conn.execute('''
                SELECT * FROM reimbursements WHERE id = ?
            ''', (reimbursement_id,)).fetchone()
            
            if not reimbursement:
                return {'success': False, 'error': '报销单不存在'}
            
            if reimbursement['status'] not in ['草稿', '已拒绝']:
                return {'success': False, 'error': '只有草稿或已拒绝状态的报销单可以添加支出记录'}
            
            # 开始事务
            conn.execute('BEGIN TRANSACTION')
            
            added_count = 0
            for expense_id in expense_ids:
                # 验证支出记录是否存在
                expense = conn.execute('''
                    SELECT * FROM expenses WHERE id = ?
                ''', (expense_id,)).fetchone()
                
                if not expense:
                    continue
                
                # 检查支出记录是否已关联到其他报销单
                existing = conn.execute('''
                    SELECT 1 FROM reimbursement_expenses WHERE expense_id = ?
                ''', (expense_id,)).fetchone()
                
                if existing:
                    continue
                
                # 添加关联（使用原始金额）
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.execute('''
                    INSERT INTO reimbursement_expenses (reimbursement_id, expense_id, reimbursement_amount, added_date)
                    VALUES (?, ?, ?, ?)
                ''', (reimbursement_id, expense_id, expense['amount'], current_time))
                
                added_count += 1
            
            conn.commit()
            return {'success': True, 'added_count': added_count}
        except sqlite3.Error as e:
            conn.rollback()
            logging.error(f"Database error in add_multiple_expenses_to_reimbursement: {e}")
            return {'success': False, 'error': '数据库操作失败'}
        except Exception as e:
            conn.rollback()
            logging.error(f"Error in add_multiple_expenses_to_reimbursement: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()
    
    def add_reimbursement_payment(self, reimbursement_id, payment_date, amount, note):
        """添加报销单回款记录"""
        conn = get_db()
        try:
            # 验证报销单是否存在
            reimbursement = conn.execute('''
                SELECT * FROM reimbursements WHERE id = ?
            ''', (reimbursement_id,)).fetchone()
            
            if not reimbursement:
                return {'success': False, 'error': '报销单不存在'}
            
            # 非草稿状态的报销单都可以添加回款
            if reimbursement['status'] == '草稿':
                return {'success': False, 'error': '草稿状态的报销单不能添加回款'}
            
            # 验证必填字段
            if not payment_date or amount is None or amount <= 0:
                return {'success': False, 'error': '回款日期和金额为必填项，金额必须大于0'}
            
            # 添加回款记录
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('''
                INSERT INTO reimbursement_payments 
                (reimbursement_id, payment_date, amount, note, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (reimbursement_id, payment_date, amount, note, current_time))
            
            # 计算总回款金额
            total_paid = conn.execute('''
                SELECT SUM(amount) as total FROM reimbursement_payments 
                WHERE reimbursement_id = ?
            ''', (reimbursement_id,)).fetchone()['total'] or 0
            
            # 更新报销单的总回款金额
            conn.execute('''
                UPDATE reimbursements SET total_paid = ? 
                WHERE id = ?
            ''', (total_paid, reimbursement_id))
            
            # 如果回款金额等于或超过报销总额，更新状态为'已回款'
            if total_paid >= reimbursement['total_amount']:
                conn.execute('''
                    UPDATE reimbursements SET status = '已回款' 
                    WHERE id = ?
                ''', (reimbursement_id,))
            
            conn.commit()
            return {'success': True}
        except Exception as e:
            conn.rollback()
            logging.error(f"Error adding reimbursement payment: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()
    
    def export_reimbursement_details(self, reimbursement_id):
        """导出报销单的费用汇总信息（按归属项目和费用类别汇总）"""
        conn = get_db()
        try:
            # 获取报销单的汇总信息，按项目和费用类别分组
            query = '''
                SELECT 
                    MIN(e.date) as min_date,
                    MAX(e.date) as max_date,
                    COALESCE(p.name, '无项目') as project_name,
                    e.category,
                    SUM(re.reimbursement_amount) as total_amount
                FROM reimbursement_expenses re
                JOIN expenses e ON re.expense_id = e.id
                LEFT JOIN projects p ON e.project_id = p.id
                WHERE re.reimbursement_id = ?
                GROUP BY p.name, e.category
                ORDER BY p.name, e.category
            '''
            
            results = conn.execute(query, (reimbursement_id,)).fetchall()
            
            # 处理日期格式，如果有多个日期则显示范围
            export_data = []
            for row in results:
                # 如果最小日期和最大日期相同，则只显示一个日期，否则显示日期范围
                if row['min_date'] == row['max_date']:
                    date_str = row['min_date']
                else:
                    date_str = f"{row['min_date']}至{row['max_date']}"
                    
                export_data.append({
                    'date': date_str,
                    'project_name': row['project_name'],
                    'category': row['category'],
                    'total_amount': row['total_amount']
                })
            
            return export_data
        except Exception as e:
            logging.error(f"Error exporting reimbursement details: {e}")
            raise DatabaseError("导出报销单详情失败")
        finally:
            conn.close()
