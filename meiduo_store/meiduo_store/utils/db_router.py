class MasterSlaveDBRouter(object):
    """创建和配置数据库读写路由"""

    def db_for_read(self, model, **hints):
        """读"""
        return "slave"

    def db_for_write(self, model, **hints):
        """写"""
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        """是否运行关联操作，表之间的关联查询"""
        return True