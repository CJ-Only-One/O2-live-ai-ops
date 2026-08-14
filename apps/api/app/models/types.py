"""모델이 공유하는 컬럼 타입.

두 가지가 MySQL 에서만 다르게 동작해서 한 곳에 모은다.
"""

from sqlalchemy import text
from sqlalchemy.dialects.mysql import DATETIME

# architecture.md 4.4 가 DATETIME(3) 을 쓴다. 제네릭 sa.DateTime 은 정밀도
# 인자를 받지 않아 DateTime(3) 이 timezone=3 으로 해석되고, 밀리초가 조용히
# 사라진 채 DATETIME 이 만들어진다.
DT3 = DATETIME(fsp=3)

# fsp 가 붙은 컬럼은 기본값도 같은 정밀도를 요구한다.
# func.now(3) 은 now(3) 으로 렌더되는데 그것은 기본값 문법이 아니라
# "Invalid default value" 로 거부된다.
NOW3 = text("CURRENT_TIMESTAMP(3)")
