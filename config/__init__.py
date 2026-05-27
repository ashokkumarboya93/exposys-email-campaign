"""
Exposys Campaign configuration package.

Ensures Celery app is loaded when Django starts.
"""
import pymysql
pymysql.install_as_MySQLdb()

from celery_app import app as celery_app

__all__ = ("celery_app",)
