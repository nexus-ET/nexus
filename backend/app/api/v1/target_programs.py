from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.target_program import TargetCourseRead, TargetProgramRead
from app.services.target_programs import (
    get_target_program_by_code,
    list_active_target_courses,
    list_active_target_programs,
)

router = APIRouter()


@router.get("/target-programs", response_model=list[TargetProgramRead])
@router.get("/target-programs/", response_model=list[TargetProgramRead])
def get_target_programs(db: Session = Depends(get_db)):
    """List active target program options for study interest forms."""
    return list_active_target_programs(db)


@router.get("/target-programs/{program_code}/courses", response_model=list[TargetCourseRead])
@router.get("/target-programs/{program_code}/courses/", response_model=list[TargetCourseRead])
def get_target_courses_for_program(program_code: str, db: Session = Depends(get_db)):
    """List active courses mapped to a target program."""
    program = get_target_program_by_code(db, program_code)
    if not program:
        raise HTTPException(status_code=404, detail="Target program not found.")
    courses = list_active_target_courses(db, program.code)
    return [
        TargetCourseRead(
            id=course.id,
            code=course.code,
            label=course.label,
            program_code=program.code,
            sort_order=course.sort_order,
        )
        for course in courses
    ]
