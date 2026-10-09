"""
Response schemas for the admin dashboard. Everything here is read-only
aggregate data — there's no request body for any admin endpoint in this
module beyond query params.
"""

from datetime import datetime

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_registered_users: int
    total_logins: int
    unique_users_logged_in: int
    admin_login_status: str


class RecentSearchOut(BaseModel):
    id: int
    user_full_name: str
    keyword: str
    language: str
    newspaper: str | None
    result_count: int
    searched_at: datetime


class RecentReportOut(BaseModel):
    id: int
    user_full_name: str
    title: str
    article_count: int
    generated_at: datetime


class UserActivityOut(BaseModel):
    id: int
    full_name: str
    email: str
    login_count: int
    last_login_at: datetime | None
    created_at: datetime


class LoginActivityOut(BaseModel):
    id: int
    user_full_name: str
    user_email: str
    login_at: datetime


class CountByLabel(BaseModel):
    label: str
    count: int


class DateCount(BaseModel):
    period: str  # "2026-07-04" for daily, "2026-07" for monthly
    count: int


class AdminDashboardOut(BaseModel):
    overview: OverviewStats
    recent_searches: list[RecentSearchOut]
    recent_reports: list[RecentReportOut]
    most_searched_keywords: list[CountByLabel]
    most_selected_language: list[CountByLabel]
    most_selected_newspaper: list[CountByLabel]
    most_selected_edition: list[CountByLabel]
    daily_reports: list[DateCount]
    monthly_reports: list[DateCount]
    login_activity: list[LoginActivityOut]


class UsersListOut(BaseModel):
    users: list[UserActivityOut]
