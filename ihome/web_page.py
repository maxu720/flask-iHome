# coding=utf-8

from flask import Blueprint, current_app, make_response, session
from flask_wtf import csrf


html = Blueprint("html", __name__)


@html.route("/<regex('.*'):file_name>")
def html_file(file_name):
    if not file_name:
        file_name = 'index.html'

    if file_name != 'favicon.ico':
        file_name = "html/" + file_name

    # 添加csrf_token保护
    csrf_token = csrf.generate_csrf()

    # 构造响应体response
    response = make_response(current_app.send_static_file(file_name))

    # 设置cookies
    response.set_cookie('csrf_token', csrf_token)

    # 返回响应体
    return response