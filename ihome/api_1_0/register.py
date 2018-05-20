# coding=utf-8
# 导入蓝图对象
from . import api
# 导入图片验证扩展
from ihome.utils.captcha.captcha import captcha
# 导入数据库实例
from ihome import redis_store, constants, db
# 导入flask内置的对象
from flask import current_app, jsonify, make_response, request, session
# 导入自定义的状态码
from ihome.utils.response_code import RET
# 导入User模型类
from ihome.models import User
# 导入云通讯扩展包
from ihome.utils import sms

# 导入正则模块
import re
# 导入random模块，构造短信随机数
import random


@api.route('/imagecode/<image_code_id>', methods=['GET'])
def generate_image_code(image_code_id):
    """
    生成图片验证码:
    1/调用captcha扩展包,生成图片验证码,name,text,image
    2/本地存储图片验证码,使用redis数据库
    3/返回图片本身,设置响应的content-type
    4/调用make_response
    :param image_code_id:
    :return:
    """
    # 调用captcha扩展包

    name, text, image = captcha.generate_captcha()
    # 调用redis数据库实例，存储图片验证码

    # 删除上一个保持在redis数据库中的图片验证码
    try:
        code_image = request.cookies.get('image_code')

    except Exception as e:
        current_app.logger.error(e)
    else:
        if code_image:
            try:
                redis_store.delete('ImageCode_'+str(code_image))  # code_image没有类型要转成字符串
            except Exception as e:
                current_app.logger.error(e)

    try:
        # 调用redis数据库实例，存储图片验证码
        # setex存储数据的类型及格式
        # setex存储数据的类型是string 基本格式setex('key','timeout(过期时间)','values(值)')
        redis_store.setex('ImageCode_'+ image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)
    except Exception as e:
        # 调用应用上下文,记录项目错误日志信息
        current_app.logger.error(e)
        # 以application/json的形式返回错误状态码,错误信息
        return jsonify(errno=RET.DBERR,errmsg='保存图片验证失败')
    # 如果未发生异常，返回图片本身
    else:
        # 使用响应对象，用来返回图片
        response = make_response(image)
        # 设置响应报文的Content-Type = 'image/jpg'
        response.headers['Content-Type'] = 'image/jpg'
        # response对象删除上一个保持在浏览器cookie中的图片验证码
        try:
            response.delete_cookie('image_code')
        except Exception as e:
            pass
        # 新的验证码存入cookie
        response.set_cookie('image_code', image_code_id)
        # 返回响应response
        return response


@api.route('/smscode/<mobile>', methods=['GET'])
def send_sms_code(mobile):
    """
    发送短信:获取参数--校验参数--查询数据--返回结果
    1/获取参数,图片验证码和编号
    2/校验参数的完整性,mobile,text,id
    3/检查mobile手机号格式
    4/获取本地存储的真实图片验证码
    5/判断获取结果,图片验证码是否过期
    6/删除图片验证码
    7/比较图片验证码
    8/生成短信内容,随机数
    9/查询数据库,判断手机号是否已经注册
    10/保存短信内容到redis中
    11/调用云通讯发送短信
    12/保存返回结果,判断是否发送成功
    13/返回结果
    :param mobile:
    :return:
    """
    # 获取参数
    image_code = request.args.get('text')
    image_code_id = request.args.get('id')
    # 检查参数的完整性，any--all
    if not all([mobile,image_code,image_code_id]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数不完整')
    # 校验手机号格式是否满足
    if not re.match(r'1[3456789]\d{9}',mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机号格式错误')
    # 检查图片验证码，获取本地存储的真实图片验证码
    try:
        real_image_code = redis_store.get('ImageCode_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询图片验证码失败')
    # 校验获取结果
    if not real_image_code:
        return jsonify(errno=RET.NODATA, errmsg='图片验证码过期')
    try:
        redis_store.delete('ImageCode_' + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
    # 比较图片验证码是否一致，忽略大小写
    if real_image_code.lower() != image_code.lower():
        return jsonify(errno=RET.DATAERR, errmsg='图片验证码错误')
    # 查询数据库，判断手机号是否已经注册
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询数据库异常')
    else:
        # 判断查询结果
        if user:
            return jsonify(errno=RET.DATAEXIST, errmsg='手机号已注册')
    # 构造短信随机码
    sms_code = '%06d' % random.randint(0, 999999)
    # 保存短信随机码
    print mobile
    print sms_code
    try:
        redis_store.setex('SMSCode_' + mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='保存短信验证码失败')
    # 调用云通讯扩展，发送短信
    try:
        ccp = sms.CCP()
        # 调用云通讯的模板方法发送短信
        result = ccp.send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES/60],1)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg='发送短信异常')
    # 判断result是否发送成功
    # result = 0
    if 0 == result:
        return jsonify(errno=RET.OK, errmsg='发送成功')
    else:
        return jsonify(errno=RET.THIRDERR, errmsg='发送失败')


@api.route('/users',methods=['POST'])
def register():
    """
    注册用户
    1/获取参数,request.get_json()
    2/校验参数存在
    3/获取详细的参数,mobile,sms_code,password
    4/校验手机号格式
    5/校验短信验证码
    6/获取本地存储的真实短信验证码
    7/判断查询结果
    8/比较短信验证码是否正确
    9/删除短信验证码
    10/保存用户数据
    user = User(mobile=mobile,name=mobile)
    user.password = password
    11/缓存用户信息
    12/返回结果

    :return:
    """
    # 获取参数
    user_data = request.get_json()
    # 判断获取结果
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数信息，mobile,sms_code,password
    # user_data['mobile']
    mobile = user_data.get('mobile')
    sms_code = user_data.get('sms_code')
    password = user_data.get('password')
    # 检查参数的完整性
    if not all([mobile, sms_code, password]):
        return jsonify(errno=RET.PARAMERR, errmsg='参数缺失')
    # 手机号格式检查
    if not re.match(r'1[3456789]\d{9}', mobile):
        return jsonify(errno=RET.PARAMERR, errmsg='手机号格式错误')
    # 判断用户是否已经注册
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询数据库异常')
    else:
        # 判断查询结果
        if user:
            return jsonify(errno=RET.DATAEXIST, errmsg='手机号已注册')
    # 获取本地存储的真实短信验证码
    try:
        real_sms_code = redis_store.get('SMSCode_' + mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg='查询数据库异常')
    # 验证码是否存在
    if not real_sms_code:
        return jsonify(errno=RET.NODATA, errmsg='短信验证码过期')
    # 直接比较短信验证是否正确
    if real_sms_code != str(sms_code):
        return jsonify(errno=RET.DATAERR, errmsg='短信验证码错误')
    # 删除短信验证码
    try:
        redis_store.delete('SMSCode_' + mobile)
    except Exception as e:
        current_app.logger.error(e)
    # 准备保存用户注册信息
    user = User(mobile=mobile,name=mobile)
    # 调用模型类中的方法generate_password_hash, 对密码进行加密sha256处理
    user.password = password
    # 提交数据到数据库
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 如果提交数据发生异常，需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg='保存用户信息失败')
    # 缓存用户信息
    session['user_id'] = user.id
    session['mobile'] = mobile
    session['name'] = mobile
    # 返回结果
    return jsonify(errno=RET.OK, errmsg='OK', data=user.to_dict())

