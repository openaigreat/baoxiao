import pandas as pd
import os
import uuid
from werkzeug.utils import secure_filename
from models import get_db
import logging
from services.exceptions import DatabaseError, FileProcessingError, ValidationError

class ExpenseService:
    def __init__(self):
        pass
    
    def read_excel_file(self, file_path, file_extension):
        """
        读取Excel或CSV文件
        :param file_path: 文件路径
        :param file_extension: 文件扩展名
        :return: DataFrame对象
        """
        if not file_path or not os.path.exists(file_path):
            raise ValidationError("文件路径无效或文件不存在")
            
        if not file_extension:
            raise ValidationError("文件扩展名不能为空")
        
        try:
            if file_extension.endswith('.csv'):
                # 尝试不同的编码格式来读取CSV文件
                try:
                    df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        df = pd.read_csv(file_path, encoding='gbk')
                    except UnicodeDecodeError:
                        try:
                            df = pd.read_csv(file_path, encoding='gb2312')
                        except:
                            raise FileProcessingError('CSV文件编码不支持，请尝试UTF-8或GBK编码格式')
            elif file_extension.endswith('.xlsx'):
                # 对于xlsx文件，强制使用openpyxl引擎
                df = pd.read_excel(file_path, engine='openpyxl')
            elif file_extension.endswith('.xls'):
                # 对于xls文件，使用xlrd引擎
                df = pd.read_excel(file_path, engine='xlrd')
            else:
                raise FileProcessingError('不支持的文件格式，请上传CSV、XLSX或XLS格式的文件')
            
            return df
        except pd.errors.ParserError as e:
            logging.error(f"Excel解析错误: {e}")
            raise FileProcessingError("文件格式解析失败，请检查文件内容是否正确")
        except Exception as e:
            logging.error(f"读取Excel文件时出错: {e}")
            raise FileProcessingError(f"文件读取失败: {str(e)}")
    
    def save_uploaded_file(self, file, upload_folder):
        """
        保存上传的文件
        :param file: 上传的文件对象
        :param upload_folder: 上传文件夹路径
        :return: 保存的文件名
        """
        if not file:
            raise ValidationError("文件对象不能为空")
            
        if not upload_folder:
            raise ValidationError("上传文件夹路径不能为空")
            
        if not os.path.exists(upload_folder):
            raise ValidationError("上传文件夹不存在")
        
        if file.filename == '':
            raise ValidationError("未选择文件")
        
        if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
            raise ValidationError("不支持的文件格式")
        
        filename = str(uuid.uuid4()) + '_' + secure_filename(file.filename)
        temp_path = os.path.join(upload_folder, filename)
        file.save(temp_path)
        return filename
    
    def process_imported_expenses(self, df, mapping, session):
        """
        处理导入的支出数据
        :param df: DataFrame对象
        :param mapping: 字段映射关系
        :param session: Flask会话对象
        :return: 成功和失败的数量
        """
        if df is None:
            raise ValidationError("数据表格不能为空")
            
        if not mapping:
            raise ValidationError("字段映射关系不能为空")
        
        conn = get_db()
        success_count = 0
        error_count = 0
        
        # 存储每行的错误信息
        row_errors = []
        
        try:
            for index, row in df.iterrows():
                try:
                    # === 日期处理 ===
                    if pd.isna(row[mapping['date_col']]):
                        row_errors.append(f"第{index+2}行: 日期为空")
                        error_count += 1
                        continue  # 跳过插入操作
                    else:
                        try:
                            date = pd.to_datetime(row[mapping['date_col']]).strftime('%Y-%m-%d')
                        except pd.errors.ParserError:
                            row_errors.append(f"第{index+2}行: 日期格式错误")
                            error_count += 1
                            continue  # 跳过插入操作
                    
                    # === 项目ID处理 ===
                    project_id = row[mapping['project_col']]
                    if pd.isna(project_id):
                        project_id = None  # 允许项目ID为空，设置为None
                    else:
                        try:
                            project_id = int(project_id)
                        except ValueError:
                            row_errors.append(f"第{index+2}行: 项目ID格式错误")
                            error_count += 1
                            continue  # 跳过插入操作
                    
                    # === 用途处理 ===
                    purpose = row[mapping['purpose_col']]
                    if pd.isna(purpose):
                        purpose = ''  # 如果为空则设置为空字符串
                    
                    # === 金额处理 ===
                    try:
                        amount_value = row[mapping['amount_col']]
                        # 格式化金额字段，移除货币符号、千位分隔符等
                        amount = self._format_amount(amount_value)
                        # 移除了金额必须大于0的检查，允许0值
                    except (ValueError, TypeError) as e:
                        row_errors.append(f"第{index+2}行: 金额格式错误 - {str(e)}")
                        error_count += 1
                        continue  # 跳过无法转换为浮点数的金额
                    
                    # === 备注处理 ===
                    note = row[mapping['note_col']]
                    if pd.isna(note):
                        note = ''  # 如果为空则设置为空字符串
                    
                    # === 分类处理 ===
                    category = row[mapping['category_col']]
                    if pd.isna(category):
                        category = '其他'  # 如果为空则设置为"其他"
                    
                    # 插入数据库
                    conn.execute('''
                        INSERT INTO expenses (date, project_id, description, amount, payment_method, category, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        date,
                        project_id,
                        purpose,
                        amount,
                        note,  # 使用payment_method列存储note内容
                        category,
                        session.get('user_id', 1)  # 使用默认用户ID 1
                    ))
                    success_count += 1
                    
                except Exception as row_error:
                    error_msg = f"第{index+2}行: 处理时发生未知错误 - {str(row_error)}"
                    row_errors.append(error_msg)
                    logging.error(error_msg)
                    error_count += 1
                    continue
            
            conn.commit()
            
            # 将错误信息存储到session中，以便在页面上显示
            if row_errors:
                session['import_errors'] = row_errors
                
            return success_count, error_count
            
        except Exception as e:
            conn.rollback()
            logging.error(f"处理导入支出时发生错误: {e}")
            raise DatabaseError(f"数据导入失败: {str(e)}")
        finally:
            conn.close()
    
    def _format_amount(self, amount_value):
        """
        格式化金额字段，处理各种可能的金额格式
        :param amount_value: 原始金额值
        :return: 格式化后的浮点数金额
        """
        # 如果金额为空，则赋值为0
        if pd.isna(amount_value) or amount_value == '':
            return 0.0
        
        # 转换为字符串进行处理
        amount_str = str(amount_value).strip()
        
        # 如果处理后是空字符串，则赋值为0
        if not amount_str:
            return 0.0
        
        # 移除常见的非数字字符（货币符号、千位分隔符等）
        # 保留数字、小数点和负号
        import re
        amount_str = re.sub(r'[^\d.-]', '', amount_str)
        
        # 处理空字符串
        if not amount_str:
            return 0.0
        
        # 转换为浮点数
        try:
            amount = float(amount_str)
            return amount
        except ValueError:
            # 如果转换失败，返回0
            return 0.0
