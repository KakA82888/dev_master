"""修改意见汇总路由（任务书 §2.2 目标 4：修改意见沉淀用于优化生成模板）。

按分类统计意见数量并给出最近明细，供报告模板与提示词的迭代参考。
"""
from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    FEEDBACK_CONCLUSION,
    FEEDBACK_FORMAT,
    FEEDBACK_METRIC,
    FEEDBACK_OTHER,
    ROLE_ADMIN,
    Feedback,
)
from ..schemas import CurrentUser, FeedbackOut
from ..security import get_current_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

CATEGORY_LABEL = {
    FEEDBACK_METRIC: "指标数值",
    FEEDBACK_CONCLUSION: "结论表述",
    FEEDBACK_FORMAT: "格式排版",
    FEEDBACK_OTHER: "其他",
}
_CATEGORY_ORDER = (FEEDBACK_METRIC, FEEDBACK_CONCLUSION, FEEDBACK_FORMAT, FEEDBACK_OTHER)


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=200),
):
    """修改意见汇总：按分类计数 + 最近 N 条明细。

    普通用户仅统计自己的意见；管理员统计全部（便于统一迭代生成模板）。
    """
    q = db.query(Feedback)
    if current_user.role != ROLE_ADMIN:
        q = q.filter(Feedback.user_id == current_user.id)
    rows = q.order_by(desc(Feedback.created_at)).all()
    counter = Counter(r.category for r in rows)
    return {
        "total": len(rows),
        "by_category": [
            {"category": c, "label": CATEGORY_LABEL[c], "count": counter.get(c, 0)}
            for c in _CATEGORY_ORDER
        ],
        "recent": [FeedbackOut.model_validate(r).model_dump() for r in rows[:limit]],
    }
