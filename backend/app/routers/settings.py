from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limit import STRICT_RATE_LIMIT, limiter
from app.db.database import get_db
from app.models.user import User
from app.schemas.settings import (
    BusinessEmailDomainResponse,
    BusinessProfileOut,
    BusinessProfileUpdateRequest,
    DynamicSettingOut,
    DynamicSettingUpdateRequest,
    DynamicSettingsResponse,
    PublicHolidayBulkRemoveRequest,
    PublicHolidayBulkSaveRequest,
    PublicHolidayRemoveRequest,
    PublicHolidaySaveRequest,
    PublicHolidayToggleRequest,
    PublicHolidaysResponse,
    BusinessTimezoneResponse,
)
from app.services import public_holiday_service, settings_service
from app.services.business_profile_service import (
    get_business_profile,
    resolve_business_id_for_user,
    update_business_profile,
)
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/settings", response_model=DynamicSettingsResponse)
@router.get("/settings/", response_model=DynamicSettingsResponse)
def list_settings(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    settings = settings_service.list_settings(db)
    return DynamicSettingsResponse(settings=[DynamicSettingOut(**item) for item in settings])


@router.get("/settings/business-timezone", response_model=BusinessTimezoneResponse)
@router.get("/settings/business-timezone/", response_model=BusinessTimezoneResponse)
def read_business_timezone(
    db: Session = Depends(get_db),
    _: User = Depends(deps.get_current_active_user),
):
    return BusinessTimezoneResponse(**settings_service.get_business_timezone_payload(db))


@router.get("/settings/business-email-domain", response_model=BusinessEmailDomainResponse)
@router.get("/settings/business-email-domain/", response_model=BusinessEmailDomainResponse)
def read_business_email_domain(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    business_id = resolve_business_id_for_user(current_user)
    profile = get_business_profile(db, business_id)
    return BusinessEmailDomainResponse(
        business_id=profile["business_id"],
        email_domain=profile["email_domain"],
    )


@router.post("/settings/update", response_model=DynamicSettingOut)
@router.post("/settings/update/", response_model=DynamicSettingOut)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("update_setting", "dynamic_setting")
def update_setting(
    request: Request,
    payload: DynamicSettingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    updated = settings_service.update_setting(
        db,
        payload.key,
        payload.value,
        updated_by_user_id=current_user.id,
    )
    return DynamicSettingOut(**updated)


@router.get("/settings/business-profile", response_model=BusinessProfileOut)
@router.get("/settings/business-profile/", response_model=BusinessProfileOut)
def read_business_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    business_id = resolve_business_id_for_user(current_user)
    return BusinessProfileOut(**get_business_profile(db, business_id))


@router.put("/settings/business-profile", response_model=BusinessProfileOut)
@router.put("/settings/business-profile/", response_model=BusinessProfileOut)
@limiter.limit(STRICT_RATE_LIMIT)
@log_action("update_business_profile", "business")
def save_business_profile(
    request: Request,
    payload: BusinessProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    business_id = resolve_business_id_for_user(current_user)
    updated = update_business_profile(
        db,
        business_id,
        business_name=payload.business_name,
        business_domain=payload.business_domain,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        address_line3=payload.address_line3,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        zip_code=payload.zip_code,
        office_phone_number=payload.office_phone_number,
        office_mobile_number=payload.office_mobile_number,
        web_url=payload.web_url,
        email_domain=payload.email_domain,
    )
    return BusinessProfileOut(**updated)


@router.get("/settings/public-holidays", response_model=PublicHolidaysResponse)
@router.get("/settings/public-holidays/", response_model=PublicHolidaysResponse)
def list_public_holidays(
    db: Session = Depends(get_db),
    _: User = Depends(deps.require_super_admin),
):
    return PublicHolidaysResponse(**public_holiday_service.get_public_holidays_payload(db))


def _parse_holiday_date(raw_date: str):
    from datetime import date as date_type

    from fastapi import HTTPException

    try:
        return date_type.fromisoformat(raw_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD format.") from exc


@router.post("/settings/public-holidays/save", response_model=PublicHolidaysResponse)
@router.post("/settings/public-holidays/save/", response_model=PublicHolidaysResponse)
@log_action("save_public_holiday", "public_holiday")
def save_public_holiday(
    request: Request,
    payload: PublicHolidaySaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    holiday_date = _parse_holiday_date(payload.date)
    updated = public_holiday_service.save_public_holiday(
        db,
        holiday_date,
        payload.name,
        updated_by_user_id=current_user.id,
    )
    return PublicHolidaysResponse(**updated)


@router.post("/settings/public-holidays/remove", response_model=PublicHolidaysResponse)
@router.post("/settings/public-holidays/remove/", response_model=PublicHolidaysResponse)
@log_action("remove_public_holiday", "public_holiday")
def remove_public_holiday(
    request: Request,
    payload: PublicHolidayRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    holiday_date = _parse_holiday_date(payload.date)
    updated = public_holiday_service.remove_public_holiday(
        db,
        holiday_date,
        updated_by_user_id=current_user.id,
    )
    return PublicHolidaysResponse(**updated)


def _parse_holiday_dates(raw_dates: list[str]) -> list:
    from datetime import date as date_type

    from fastapi import HTTPException

    if not raw_dates:
        raise HTTPException(status_code=400, detail="Select at least one date.")

    parsed: list[date_type] = []
    seen: set[date_type] = set()
    for raw_date in raw_dates:
        try:
            holiday_date = date_type.fromisoformat(raw_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date '{raw_date}'. Use YYYY-MM-DD format.",
            ) from exc
        if holiday_date in seen:
            continue
        parsed.append(holiday_date)
        seen.add(holiday_date)
    return parsed


@router.post("/settings/public-holidays/bulk-save", response_model=PublicHolidaysResponse)
@router.post("/settings/public-holidays/bulk-save/", response_model=PublicHolidaysResponse)
@log_action("bulk_save_public_holidays", "public_holiday")
def bulk_save_public_holidays(
    request: Request,
    payload: PublicHolidayBulkSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    holiday_dates = _parse_holiday_dates(payload.dates)
    updated = public_holiday_service.bulk_save_public_holidays(
        db,
        holiday_dates,
        payload.name,
        updated_by_user_id=current_user.id,
    )
    return PublicHolidaysResponse(**updated)


@router.post("/settings/public-holidays/bulk-remove", response_model=PublicHolidaysResponse)
@router.post("/settings/public-holidays/bulk-remove/", response_model=PublicHolidaysResponse)
@log_action("bulk_remove_public_holidays", "public_holiday")
def bulk_remove_public_holidays(
    request: Request,
    payload: PublicHolidayBulkRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    holiday_dates = _parse_holiday_dates(payload.dates)
    updated = public_holiday_service.bulk_remove_public_holidays(
        db,
        holiday_dates,
        updated_by_user_id=current_user.id,
    )
    return PublicHolidaysResponse(**updated)


@router.post("/settings/public-holidays/toggle", response_model=PublicHolidaysResponse)
@router.post("/settings/public-holidays/toggle/", response_model=PublicHolidaysResponse)
@log_action("toggle_public_holiday", "public_holiday")
def toggle_public_holiday(
    request: Request,
    payload: PublicHolidayToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    holiday_date = _parse_holiday_date(payload.date)
    updated = public_holiday_service.toggle_public_holiday(
        db,
        holiday_date,
        updated_by_user_id=current_user.id,
    )
    return PublicHolidaysResponse(**updated)
