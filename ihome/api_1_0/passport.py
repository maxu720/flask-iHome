# coding=utf-8
# 导入蓝图对象
from flask import make_response

from . import api
# 导入flask封装的对象
from flask import request,jsonify,current_app,session,g
# 导入自定义的状态码
from ihome.utils.response_code import RET
# 导入模型类
from ihome.models import User
# 导入登陆验证装饰器
from ihome.utils.commons import login_required
# 导入数据库实例
from ihome import db,constants
# 导入七牛云
from ihome.utils.image_storage import storage

# 导入正则模块
import re


@api.route('/sessions',methods=['POST'])
def login():
    """
    用户登陆
    1/获取参数,request.get_json()
    2/检查获取结果
    3/获取json数据包的详细参数信息,mobile/password
    4/检查参数的完整性
    5/检查手机号的格式
    6/查询数据库,确认用户已注册,保存查询结果
    7/密码检查:使用模型类对象调用密码检查方法check_password_hash(password)
    user.password = password --->generate_password_hash
    8/缓存用户信息:
    session['name'] = mobile
    session['name'] = user.name
    9/返回结果
    :return:
    """
    # 获取参数post请求
    user_data = request.get_json()
    # 校验参数的存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数信息,mobile,password
    mobile = user_data.get('mobile')
    password = user_data.get('password')
    # 检查参数的完整性
    if not all([mobile,password]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数不完整')
    # 校验手机号格式
    if not re.match(r'1[3456789]\d{9}',mobile):
        return jsonify(errno=RET.PARAMERR,errmsg='手机号格式错误')
    # 查询数据库,确认用户的存在,保存查询结果
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询数据库异常')
    # 校验查询结果,确认用户已注册/确认密码正确
    if user is None or not user.check_password(password):
        return jsonify(errno=RET.DATAERR,errmsg='用户名或密码错误')
    # 缓存用户信息
    """
    如果要实现状态保持:
    def login_required():
        user_id = session.get('user_id')
        if user_id:
            g.user_id = user_id
        else:
            return jsonify(errno=RET.SESSIONERR,errmsg='用户未登陆')

    """
    session['user_id'] = user.id
    session['mobile'] = mobile
    # 如果用户修改了用户名信息,不能指定用户名为手机号
    session['name'] = user.name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'user_id':user.id})


@api.route('/user', methods=['GET'])
@login_required
def get_user_profile():
    """
    获取用户信息
    1/获取用户身份
    user_id = g.user_id
    2/根据用户身份查询数据库
    user = User.query.get(user_id)
    user = User.query.filter_by(id=user_id).first()
    3/校验查询结果
    4/返回结果,需要调用模型类中to_dict()方法
    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 查询mysql数据库
    try:
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询数据库错误')
    # 判断查询结果
    if not user:
        return jsonify(errno=RET.NODATA,errmsg='未查询到数据')
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data=user.to_dict())


@api.route('/user/name', methods=['PUT'])
@login_required
def change_user_profile():
    """
    修改用户信息
    1/获取用户身份
    2/获取参数,put请求里的json数据,request.get_json()
    3/判断获取结果是否有数据
    4/获取详细的参数信息,name
    5/查询数据库,执行update更新用户信息
    User.query.filter_by(id=user_id).update({'name':name})
    db.session.commit()
    6/更新缓存中的用户信息
    session['name'] = name
    7/返回结果

    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 获取参数
    user_data = request.get_json()
    # 检查参数存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数信息
    name = user_data.get('name')
    # 检查参数存在
    if not name:
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 更新用户的姓名信息
    try:
        User.query.filter_by(id=user_id).update({'name':name})
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 写入数据如果发生异常需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存用户信息异常')
    # 更新缓存中的用户信息
    session['name'] = name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'name':name})


@api.route('/user/avatar',methods=['POST'])
@login_required
def set_user_avatar():
    """
    设置用户头像
    1/确认用户身份
    2/获取参数,前端传过来的图片文件,request.files.get('avatar')
    3/读取图片文件对象的数据
    4/调用七牛云接口,上传用户头像
    5/保存上传的结果,七牛云会对图片文件名进行编码处理
    6/根据用户身份,保存用户头像的文件名
    7/拼接图片的绝对路径
    8/返回结果
    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 获取前端传输过来的图片文件
    avatar = request.files.get('avatar')
    # 读取图片文件,转成七牛云能接收的bytes类型
    avatar_data = avatar.read()
    # 调用七牛云,实现图片上传
    try:
        image_name = storage(avatar_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg='上传图片失败')
    # 把图片文件名保存到mysql数据库中
    # db.session.add(user)
    # 如果使用update不需要添加数据库会话对象
    try:
        # update()
        User.query.filter_by(id=user_id).update({'avatar_url':image_name})
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存用户头像失败')
    # 拼接图片的绝对路径
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={"avatar_url":image_url})


# @api.route('/user/auths',methods=['GET'])
# @login_required
# def get_user_auth():
#     """
#     获取user_id
#     判断user_id是存在与否
#     查询User中real_name和id_card是否为空
#     返回结果
#     :return:
#     """
#     # 获取user_id
#     user_id = g.user_id
#     # 判断user_id是否为空
#     if not user_id:
#         return jsonify(errno=RET.PARAMERR, errmsg='参数缺失')
#
#     # 查询数据库
#     try:
#         user = User.query.filter_by(id=user_id).first()
#     except Exception as e:
#         current_app.logger.error(e)
#         return jsonify(errno=RET.DATAERR,errmsg='查询数据库异常')
#     if not user:
#         return jsonify(errno=RET.DATAERR,errmsg='当前数据不存在')
#     else:
#         if user.real_name and user.id_card is not None:
#             return jsonify(errno=RET.PARAMERR, errmsg='当前已经注册过了')
#
#     return jsonify(errno=RET.OK, errmsg='OK')


@api.route('/user/auth',methods=['POST'])
@login_required
def set_user_auth():
    """
    设置用户实名信息:
    1/获取用户id
    2/获取参数post
    3/检查参数的存在
    4/获取详细的实名信息,real_name/id_card
    5/把用户实名信息写入到数据库中,确保实名认证只能执行一次
    User.query.filter_by(id=user_id,real_name=None,id_card=None).update({'......'})
    6/返回结果
    :return:
    """
    # 获取用户身份
    user_id = g.user_id
    # 获取post请求的json字符串
    user_data = request.get_json()
    # 判断获取结果
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数信息
    real_name = user_data.get('real_name')
    id_card = user_data.get('id_card')
    # 检查参数的完整性
    if not all([real_name,id_card]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 保存用户的实名信息到mysql数据库中
    try:
        User.query.filter_by(id=user_id,real_name=None,id_card=None).update({'real_name':real_name,'id_card':id_card})
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()

        return jsonify(errno=RET.DBERR,errmsg='保存用户实名信息失败')
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK')


@api.route('/user/auth', methods=['GET'])
@login_required
def get_user_auth():
    """
    获取用户的实名信息
    1/获取用户身份id
    2/查询mysql数据库,确认用户的存在
    3/检查结果
    4/返回结果,用户的实名信息
    :return:
    """
    # 使用g对象获取用户id
    user_id = g.user_id
    # 查询数据库
    try:
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询用户实名信息失败')
    # 判断查询结果
    if not user:
        return jsonify(errno=RET.NODATA, errmsg='无效操作')
    # 返回结果
    return jsonify(errno=RET.OK, errmsg='OK', data=user.auth_to_dict())


@api.route('/session', methods=['GET'])
def cheack_user_login():
    """
    检查用户登陆状态
    1/从redis缓存中获取用户缓存用户名信息
    2/判断获取结果是否存在
    3/返回结果
    :return:
    """
    # 使用session对象获取用户名
    name = session.get('name')
    # 判断获取结果,如果用户已经登陆,返回用户名
    if not name:
        return jsonify(errno=RET.NODATA, errmsg='无用户信息')
    # 否则返回false
    else:
        return jsonify(errno=RET.OK, errmsg='OK', data={"name":name})


@api.route('/session', methods=['DELETE'])
@login_required
def user_logout():
    """
    用户退出
    退出的本质相当于服务器清除用户的缓存信息
    :return:
    """
    try:
        session.clear()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg='登出失败')
    # 返回json响应
    return jsonify(errno=RET.OK, errmsg='OK')
