# coding=utf-8
# 导入蓝图对象
from . import api
# 导入redis实例
from ihome import redis_store,constants,db
# 导入flask内置的对象
from flask import current_app,jsonify,g,request,session
# 导入模型类
from ihome.models import Area,House,Facility,HouseImage,User,Order
# 导入自定义的状态码
from ihome.utils.response_code import RET
# 导入登陆验证装饰器
from ihome.utils.commons import login_required
# 导入七牛云
from ihome.utils.image_storage import storage


# 导入json模块
import json
# 导入日期模块
import datetime

@api.route("/areas",methods=['GET'])
def get_areas_info():
    """
    获取城区信息:
    缓存----磁盘----缓存
    1/尝试从redis中获取城区信息
    2/判断查询结果是否有数据,如果有数据
    3/留下访问redis的中城区信息的记录,在日志中
    4/需要查询mysql数据库
    5/判断查询结果
    6/定义容器,存储查询结果
    7/遍历查询结果,添加到列表中
    8/对查询结果进行序列化,转成json
    9/存入redis缓存中
    10/返回结果
    :return:
    """
    # 尝试从redis中获取程序信息
    try:
        areas = redis_store.get('area_info')
    except Exception as e:
        current_app.logger.error(e)
        # 如果查询发生异常,把查询结果置为None
        areas = None
    # 判断查询结果存在
    if areas:
        # 留下访问redis数据库的记录
        current_app.logger.info('hit redis areas info')
        return '{"errno":0,"errmsg":"OK","data":%s}' % areas
    # 查询mysql数据库
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询城区信息异常')
    # 判断查询结果,areas是查询到城区信息对象
    if not areas:
        return jsonify(errno=RET.NODATA,errmsg='无城区信息')
    # 定义容器,遍历查询结果
    areas_list = []
    for area in areas:
        # 需要调用模型类中的to_dict方法,把具体的查询对象转成键值形式的数据
        areas_list.append(area.to_dict())
    # 把城区信息转成json
    areas_json = json.dumps(areas_list)
    # 存入到redis中
    try:
        redis_store.setex('area_info',constants.AREA_INFO_REDIS_EXPIRES,areas_json)
    except Exception as e:
        current_app.logger.error(e)
    # 返回结果,城区信息已经是json字符串,不需要使用jsonify
    resp = '{"errno":0,"errmsg":"OK","data":%s}' % areas_json
    return resp

@api.route('/houses',methods=['POST'])
@login_required
def save_house_info():
    """
    发布新房源
    1/确认用户身份id
    2/获取参数,get_json()
    3/判断数据的存在
    4/获取详细的参数信息,指房屋的基本信息,不含配套设施title,price/area_id/address/unit/acreage/cacacity/beds/deposit/min_days/max_days/
    5/检查参数的完整性
    6/对价格参数进行转换,由元转成分
    7/构造模型类对象,准备存储数据
    8/判断配套设施的存在
    9/需要对配套设施进行过滤查询,后端只会保存数据库中已经定义的配套设施信息
    facilites = Facility.query.filter(Facility.id.in_(facility)).all()
    house.facilities = facilities
    10/保存数据到数据库中
    11/返回结果,house.id,让后面上传房屋图片和房屋进行关联
    :return:
    """
    # 确认用户身份
    user_id = g.user_id
    # 获取参数post
    house_data = request.get_json()
    # 检查参数的存在
    if not house_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的房屋参数信息(基本信息,除配套设施外)
    title = house_data.get('title') # 房屋标题
    area_id = house_data.get('area_id') # 房屋城区
    address = house_data.get('address') # 详细地址
    price = house_data.get('price') # 房屋价格
    room_count = house_data.get('room_count') # 房屋数目
    acreage = house_data.get('acreage') # 房屋面积
    unit = house_data.get('unit') # 房屋户型
    capacity = house_data.get('capacity') # 人数上限
    beds = house_data.get('beds') # 卧床配置
    deposit = house_data.get('deposit') # 押金
    min_days = house_data.get('min_days') # 最小入住天数
    max_days = house_data.get('max_days') # 最大入住天数
    # 检查参数的完整性
    if not all([title,area_id,address,price,room_count,acreage,unit,capacity,beds,deposit,min_days,max_days]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 对价格参数进行转换,由元转成分
    try:
        price = int(float(price)*100)
        deposit = int(float(deposit)*100)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR,errmsg='价格数据错误')
    # 构造模型类对象,准备存储数据
    house = House()
    house.user_id = user_id
    house.area_id = area_id
    house.title = title
    house.address = address
    house.price = price
    house.room_count = room_count
    house.acreage = acreage
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.deposit = deposit
    house.min_days = min_days
    house.max_days = max_days
    # 尝试获取房屋配套设施参数
    facility = house_data.get('facility')
    # 判断配套设施存在
    if facility:
        # 查询数据库,对房屋配套设施进行过滤查询,确保配套设施的编号在数据库中存在
        try:
            facilities = Facility.query.filter(Facility.id.in_(facility)).all()
            # 保存房屋配套设施信息,配套设施的数据存在第三张表,关系引用在数据库中没有具体的字段
            house.facilities = facilities
        except Exception as e:
            current_app.logger.error(e)
            return jsonify(errno=RET.DBERR,errmsg='查询配套设施异常')
    # 保存房屋数据到mysql数据库中
    try:
        db.session.add(house)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存房屋数据失败')
    # 返回结果,house.id是用来后面实现上传房屋图片做准备
    return jsonify(errno=RET.OK,errmsg='OK',data={'house_id':house.id})

@api.route('/houses/<int:house_id>/images',methods=['POST'])
@login_required
def save_house_image(house_id):
    """
    上传房屋图片
    1/获取参数,image_data = request.files属性
    2/判断获取结果
    3/根据house_id查询数据库,House模型类,
    4/判断查询结果,确认房屋的存在
    5/读取图片数据
    6/调用七牛云接口,上传图片
    7/保存图片名称
    8/构造HouseImage模型类对象,准备存储房屋图片数据
    house_image = HouseImage()
    house_image.house_id = house.id
    house_image.url = image_name
    db.session.add(house_image)
    9/判断房屋默认图片是否设置,如未设置,默认添加当前图片为主图片;
    10/保存房屋对象数据,db.session.add(house)
    11/提交数据到数据库中
    db.session.commit()
    12/拼接图片的绝对路径
    13/返回结果
    :param house_id:
    :return:
    """
    # 获取图片文件
    house_image = request.files.get('house_image')
    # 校验参数的存在
    if not house_image:
        return jsonify(errno=RET.PARAMERR,errms='未上传房屋图片')
    # 确认房屋的存在
    try:
        house = House.query.filter_by(id=house_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋数据失败')
    # 判断查询结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg='房屋不存在')
    # 读取图片数据
    house_image_data = house_image.read()
    # 调用七牛云接口,上传房屋图片
    try:
        image_name = storage(house_image_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg='上传图片失败')
    # 保存房屋图片数据,构造模型类对象
    house_image = HouseImage()
    house_image.house_id = house_id
    house_image.url = image_name
    # 添加数据到数据库会话对象
    db.session.add(house_image)
    # 判断房屋主图片是否设置,如未设置默认添加当前图片为主图片
    if not house.index_image_url:
        house.index_image_url = image_name
        db.session.add(house)
    # 提交数据到mysql数据库中
    try:
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存房屋图片数据失败')
    # 拼接图片的绝对路径
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'url':image_url})

@api.route('/user/houses',methods=['GET'])
@login_required
def get_user_houses():
    """
    我的房源
    1/确认用户身份
    2/根据用户id查询数据库
    3/使用关系定义返回的对象,实现一对多的查询,
    4/定义容器
    5/遍历查询结果,调用模型类中的方法
    6/返回数据
    :return:
    """
    # 获取用户id
    user_id = g.user_id
    # 查询mysql数据库,确认用户的存在
    try:
        # User.query.filter_by(id=user_id).first()
        user = User.query.get(user_id)
        # 使用反向引用,实现一对多的查询,获取该用户发布的所有房屋信息
        houses = user.houses
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户房屋数据失败')
    # 首先定义容器
    houses_list = []
    # 如果房屋数据存在,遍历查询结果,添加到列表中
    if houses:
        for house in houses:
            houses_list.append(house.to_basic_dict())
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'houses':houses_list})

@api.route('/houses/index',methods=['GET'])
def get_houses_index():
    """
    项目首页幻灯片
    缓存----磁盘----缓存
    1/尝试查询redis数据库,获取项目首页信息
    2/判断查询结果
    3/如果有数据,留下访问的记录,直接返回
    4/查询mysql数据库
    5/默认采取房屋成交次数最高的五套房屋
    houses = House.query.order_by(House.order_count.desc()).limit(5)
    6/判断查询结果
    7/定义容器存储查询结果
    8/遍历查询结果,判断房屋是否有主图片,如未设置默认不添加
    9/调用模型类中方法house.to_basic_dict()
    10/把房屋数据转成json字符串
    11/存入redis缓存中
    12/返回结果
    :return:
    """
    # 尝试从redis缓存中获取首页幻灯片信息
    try:
        ret = redis_store.get('home_page_data')
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断获取结果
    if ret:
        # 留下访问redis数据库的记录
        current_app.logger.info('hit redis houses index info')
        return '{"errno":0,"errmsg":"OK","data":%s}' % ret
    # 如未获取,需要查询mysql数据库
    try:
        # 默认采取的操作是按照房屋成交次数进行排序,并且使用limit分页五条房屋数据
        houses = House.query.order_by(House.order_count.desc()).limit(constants.HOME_PAGE_MAX_HOUSES)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋数据失败')
    # 判断查询结果
    if not houses:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 定义容器,遍历存储查询结果
    houses_list = []
    for house in houses:
        # 如果房屋未设置主图片,默认不添加
        if not house.index_image_url:
            continue
        houses_list.append(house.to_basic_dict())
    # 把房屋数据转成json
    houses_json = json.dumps(houses_list)
    # 存入到redis缓存中
    try:
        redis_store.setex('home_page_data',constants.HOME_PAGE_DATA_REDIS_EXPIRES,houses_json)
    except Exception as e:
        current_app.logger.error(e)
    # 构造响应报文,返回幻灯片信息
    resp = '{"errno":0,"errmsg":"OK","data":%s}' % houses_json
    return resp

@api.route('/houses/<int:house_id>',methods=['GET'])
def get_house_detail(house_id):
    """
    获取房屋详情数据
    缓存----磁盘----缓存
    1/确认访问接口的用户身份
    user_id = session.get('user_id',-1)
    2/判断house_id参数的存在
    3/尝试读取redis缓存,获取房屋详情数据
    4/判断获取结果
    5/如未获取,读取mysql数据库
    6/判断获取结果
    7/调用模型类中的方法,house.to_full_dict()
    8/转成json数据
    9/存入redis缓存中
    10/构造响应数据返回结果

    :param house_id:
    :return:
    """
    # 使用session对象获取用户身份
    user_id = session.get('user_id',-1)
    # 判断house_id存在
    if not house_id:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 尝试读取redis数据库,获取房屋详情数据
    try:
        ret = redis_store.get('house_info_%s' % house_id)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断获取结果
    if ret:
        # 留下访问redis的记录
        current_app.logger.info('hit redis house detail info')
        return '{"errno":0,"errmsg":"OK","data":{"user_id":%s,"house":%s}}' % (user_id,ret)
    # 查询磁盘数据库
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋数据失败')
    # 判断查询结果
    if not house:
        return jsonify(errno=RET.NODATA,errmsg='无房屋数据')
    # 调用模型类中的to_ful_dict()方法,因为该方法中查询了数据库,所以需要异常处理
    try:
        house_data = house.to_full_dict()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋详情数据失败')
    # 转成json
    house_json = json.dumps(house_data)
    # 把房屋详情数据存入redis缓存中
    try:
        redis_store.setex('house_info_%s' % house_id,constants.HOME_PAGE_DATA_REDIS_EXPIRES,house_json)
    except Exception as e:
        current_app.logger.error(e)
    # 构造响应报文,返回结果
    resp = '{"errno":0,"errmsg":"OK","data":{"user_id":%s,"house":%s}}' % (user_id,house_json)
    return resp

@api.route("/houses",methods=['GET'])
def get_houses_list():
    """
    获取房屋列表信息
    缓存----磁盘----缓存
    获取参数---检查参数---查询数据---返回结果
    1/获取参数:aid,sd,ed,sk,p
    2/需要对排序条件和页面两个参数,进行默认处理
    3/需要对日期参数进行判断,并且进行格式化
    4/需要对页数进行格式化
    5/尝试从redis缓存中获取房屋列表信息
    6/让一个键对应多条数据的存储,需要hash数据类型,构造hash对象的键
    redis_key = 'houses_%s_%s_%s_%s' %(aid,sd,ed,sk)
    ret = redis_store.hget(redis_key,page)
    7/如果有数据,留下访问的记录,直接返回
    8/查询mysql数据库
    9/首先定义容器存储查询数据库的过滤条件
    10/判断区域参数的存在,如果有把区域信息添加到列表中
    11/需要判断日期参数的存在,把用户选择的日期和订单表中的日期进行比较,找到日期不冲突的房屋返回给客户端
    12/根据容器中存储的过滤条件,执行查询排序,price/crate_time
    houses = House.query.filter(过滤条件).order_by(House.order_count.desc())
    13/对排序结果进行分页
    houses_page = houses.paginate(page,每页条目数,False)
    total_page = houses_page.pages
    houses_list = houses_page.items
    14/定义容器,houses_dict_list遍历分页后的房屋数据,调用模型类中的to_basic_dict()方法
    15/构造响应报文
    resp = {"errno":0,"errmsg":"OK","data":{"houses":houses_dict_list,"total_page":total_page,"current_page":page}}
    16/序列化数据,准备存入缓存中
    resp_json = json.dumps(resp)
    17/判断用户选择的页数必须小于等于分页后的总页数,本质上用户选择的页数必须要有数据
    18/构造hash数据类型的键,为了确保数据的完整性以及有效期的一致性
    需要使用事务
    pip = redis_store.pipline()
    pip.multi()
    pip.hset(redis_key,page,resp_json)
    pip.expire(redis_key,7200)
    pip.execute()
    19/返回结果,return resp_json
    :return:
    """
    # 获取参数,区域信息/开始日期/结束日期/排序条件/页数
    area_id = request.args.get('aid','')
    start_date_str = request.args.get('sd','')
    end_date_str = request.args.get('ed','')
    sort_key = request.args.get('sk','new')
    page = request.args.get('p','1')
    # 检查日期参数
    try:
        # 定义变量存储格式化后的日期
        start_date,end_date = None,None
        # 如果用户选择了开始日期
        if start_date_str:
            start_date = datetime.datetime.strptime(start_date_str,'%Y-%m-%d')
        # 如果用户选择了结束日
        if end_date_str:
            end_date = datetime.datetime.strptime(end_date_str,'%Y-%m-%d')
        # 如果用户既选择了开始日期,也选择了结束日期,判断用户选择的日期必须至少是一天
        if start_date_str and end_date_str:
            # 断言用户选择的日期必须至少是一天
            assert start_date <= end_date
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR,errmsg='日期格式错误')
    # 对页数进行格式化
    try:
        page = int(page)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR,errmsg='页数格式错误')
    # 尝试从redis缓存中获取房屋列表信息
    # 一个键对应多条数据,使用hash数据类型
    try:
        redis_key = 'houses_%s_%s_%s_%s' % (area_id,start_date_str,end_date_str,sort_key)
        ret = redis_store.hget(redis_key,page)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    # 判断ret是否存在
    if ret:
        # 留下访问redis数据的记录
        current_app.logger.info('hit redis houses list info')
        return ret
    # 查询mysql数据库
    try:
        # 定义容器,存储过滤条件
        params_filter = []
        # 如果城区参数存在
        if area_id:
            # 添加的是城区数据的对象
            params_filter.append(House.area_id == area_id)
        # 如果开始日期和结束日期参数存在,目标是查询日期不冲突的房屋
        if start_date and end_date:
            # 查询日期冲突的订单
            conflict_orders = Order.query.filter(Order.begin_date<=end_date,Order.end_date>=start_date).all()
            # 遍历日期有冲突的订单,获取有冲突的房屋
            conflict_houses_id = [order.house_id for order in conflict_orders]
            # 判断有冲突的房屋是否存在,对有冲突的房屋进行取反,获取日期不冲突的房屋
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 如果用户只选择了一个开始日期
        elif start_date:
            conflict_orders = Order.query.filter(Order.end_date>=start_date).all()
            conflict_houses_id = [order.house_id for order in conflict_orders]
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 如果用户值选择了一个结束日期
        elif end_date:
            conflict_orders = Order.query.filter(Order.begin_date<=end_date).all()
            conflict_houses_id = [order.house_id for order in conflict_orders]
            if conflict_houses_id:
                params_filter.append(House.id.notin_(conflict_houses_id))
        # 判断排序条件,按照房屋成交次数排序
        if 'booking' == sort_key:
            # *params_filter是往查询方法进行拆包
            houses = House.query.filter(*params_filter).order_by(House.order_count.desc())
        # 按照价格进行升序和降序排序
        elif 'price-inc' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.price.asc())
        elif 'price-des' == sort_key:
            houses = House.query.filter(*params_filter).order_by(House.price.desc())
        # 默认按照房屋房屋时间
        else:
            houses = House.query.filter(*params_filter).order_by(House.create_time.desc())
        # 对排序后的房屋进行分页,page代表页数,每页条目书,False分页异常不报错
        houses_page = houses.paginate(page,constants.HOUSE_LIST_PAGE_CAPACITY,False)
        print '111111',houses_page
        # 获取分页后的房屋数据
        houses_list = houses_page.items
        print '22222',houses_list
        # 获取分页后的总页数
        total_page = houses_page.pages
        print '33333',total_page
        # 定义容器,遍历分页后的房屋数据,需要调用模型类中的方法
        houses_dict_list = []
        for house in houses_list:
            houses_dict_list.append(house.to_basic_dict())
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询房屋列表信息失败')
    # 构造响应数据
    resp = {"errno":0,"errmsg":"OK","data":{"houses":houses_dict_list,"total_page":total_page,"current_page":page}}
    # 序列化数据,准备存入缓存中
    resp_json = json.dumps(resp)
    # 判断用户请求的页数必须小于等于分页后的总页数
    if page <= total_page:
        redis_key = 'houses_%s_%s_%s_%s' % (area_id,start_date_str,end_date_str,sort_key)
        # 多条数据的存储,为了确保数据的完整性和一致性,需要使用事务
        pip = redis_store.pipeline()
        try:
            # 开启事务
            pip.multi()
            # 保存数据
            pip.hset(redis_key,page,resp_json)
            # 设置过期时间
            pip.expire(redis_key,constants.HOUSE_LIST_REDIS_EXPIRES)
            # 执行事务
            pip.execute()
        except Exception as e:
            current_app.logger.error(e)
    # 返回结果
    return resp_json






