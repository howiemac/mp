""" overrides for evoke User object

    auto login as admin, no security checking
"""

from evoke.User import User as baseUser

class User(baseUser):

  def permitted(self,user):
    "always permitted..."
    return True

  def can(self,what):
    "always permitted..."
    return True

  @classmethod
  def validated_user(cls,req):
    "force user id to be admin"  
#    return cls.fetch_user('guest')
    return cls.fetch_user('admin')

