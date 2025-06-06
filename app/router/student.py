from fastapi import APIRouter, HTTPException, Request
import requests
from settings import settings
from router import (
    group,
    auth_group,
    batch,
    group_user,
    user,
    school,
    grade,
    exam,
)
from auth_group_classes import EnableStudents
from request import build_request
from routes import student_db_url
from helpers import (
    db_request_token,
    validate_and_build_query_params,
    is_response_valid,
    is_response_empty,
)
from logger_config import get_logger
from dateutil.relativedelta import relativedelta
from datetime import datetime
from mapping import (
    USER_QUERY_PARAMS,
    STUDENT_QUERY_PARAMS,
    ENROLLMENT_RECORD_PARAMS,
    SCHOOL_QUERY_PARAMS,
    authgroup_state_mapping,
)

router = APIRouter(prefix="/student", tags=["Student"])
logger = get_logger()


def process_exams(student_exam_texts):
    student_exam_ids = []
    for exam_name in student_exam_texts:
        exam_id = exam.get_exam(build_request(query_params={"name": exam_name}))["id"]
        student_exam_ids.append(exam_id)

    return student_exam_ids


def build_student_and_user_data(student_data):
    data = {}
    for key in student_data.keys():
        if key in STUDENT_QUERY_PARAMS + USER_QUERY_PARAMS:
            if key == "physically_handicapped":
                data[key] = "true" if student_data[key] == "Yes" else "false"
            elif key == "has_category_certificate":
                data[key] = "true" if student_data[key] == "Yes" else "false"
            elif key == "planned_competitive_exams":
                data[key] = process_exams(student_data[key])
            else:
                data[key] = student_data[key]
    return data


async def create_school_user_record(data, school_name, district, auth_group_name):
    state = authgroup_state_mapping.get(auth_group_name, "")

    if state:
        school_data = school.get_school(
            build_request(
                query_params={
                    "name": str(school_name),
                    "district": str(district),
                    "state": state,
                }
            )
        )
    else:
        school_data = school.get_school(
            build_request(
                query_params={"name": str(school_name), "district": str(district)}
            )
        )

    group_data = group.get_group(
        build_request(query_params={"child_id": school_data["id"], "type": "school"})
    )

    await group_user.create_group_user(
        build_request(
            method="POST",
            body={
                "group_id": group_data[0]["id"],
                "user_id": data["user"]["id"],
                "academic_year": "2025-2026",  # hardcoding; will figure better sol later
                "start_date": datetime.now().strftime("%Y-%m-%d"),
            },
        )
    )


async def create_batch_user_record(data, batch_id):
    batch_data = batch.get_batch(build_request(query_params={"batch_id": batch_id}))
    group_data = group.get_group(
        build_request(query_params={"child_id": batch_data["id"], "type": "batch"})
    )

    await group_user.create_group_user(
        build_request(
            method="POST",
            body={
                "group_id": group_data[0]["id"],
                "user_id": data["user"]["id"],
                "academic_year": "2025-2026",  # hardcoding; will figure better sol later
                "start_date": datetime.now().strftime("%Y-%m-%d"),
            },
        )
    )


async def create_grade_user_record(data):
    group_data = group.get_group(
        build_request(query_params={"child_id": data["grade_id"], "type": "grade"})
    )

    await group_user.create_group_user(
        build_request(
            method="POST",
            body={
                "group_id": group_data[0]["id"],
                "user_id": data["user"]["id"],
                "academic_year": "2025-2026",  # hardcoding; will figure better sol later
                "start_date": datetime.now().strftime("%Y-%m-%d"),
            },
        )
    )


async def create_auth_group_user_record(data, auth_group_name):
    auth_group_data = auth_group.get_auth_group(
        build_request(query_params={"name": auth_group_name})
    )
    group_data = group.get_group(
        build_request(
            query_params={"child_id": auth_group_data["id"], "type": "auth_group"}
        )
    )

    await group_user.create_group_user(
        build_request(
            method="POST",
            body={
                "group_id": group_data[0]["id"],
                "user_id": data["user"]["id"],
                "academic_year": "2025-2026",  # hardcoding; will figure better sol later
                "start_date": datetime.now().strftime("%Y-%m-%d"),
            },
        )
    )


def create_new_student_record(data):
    response = requests.post(student_db_url, json=data, headers=db_request_token())
    if is_response_valid(response, "Student API could not post the data!"):
        created_student_data = is_response_empty(
            response.json(), "Student API could fetch the created student"
        )

        return created_student_data


def check_if_email_or_phone_is_part_of_request(query_params):
    if (
        "email" not in query_params
        or query_params["email"] == ""
        or query_params["email"] is None
    ) and (
        "phone" not in query_params
        or query_params["phone"] == ""
        or query_params["phone"] is None
    ):
        raise HTTPException(
            status_code=400, detail="Email/Phone is not part of the request data"
        )
    return


def check_if_student_id_is_part_of_request(query_params):
    if (
        "student_id" not in query_params
        or query_params["student_id"] == ""
        or query_params["student_id"] is None
    ):
        raise HTTPException(
            status_code=400, detail="Student ID is not part of the request data"
        )
    return


@router.get("/")
def get_students(request: Request):
    query_params = validate_and_build_query_params(
        request.query_params,
        STUDENT_QUERY_PARAMS + USER_QUERY_PARAMS + ENROLLMENT_RECORD_PARAMS,
    )

    response = requests.get(
        student_db_url, params=query_params, headers=db_request_token()
    )
    if is_response_valid(response, "Student API could not fetch the student!"):
        return is_response_empty(response.json(), False, "Student does not exist")


@router.get("/verify")
async def verify_student(request: Request, student_id: str):
    query_params = validate_and_build_query_params(
        request.query_params,
        STUDENT_QUERY_PARAMS + USER_QUERY_PARAMS + ["auth_group_id"],
    )

    response = requests.get(
        student_db_url,
        params={"student_id": student_id},
        headers=db_request_token(),
    )
    if is_response_valid(response):
        student_data = is_response_empty(response.json(), False)

        if student_data:
            student_data = student_data[0]
            for key, value in query_params.items():
                if key in USER_QUERY_PARAMS and student_data["user"].get(key) != value:
                    return False
                if key in STUDENT_QUERY_PARAMS and student_data.get(key) != value:
                    return False

                # check if the user belongs to the auth-group that sent the validation request
                if key == "auth_group_id":
                    response = group.get_group(
                        build_request(
                            query_params={
                                "child_id": query_params["auth_group_id"],
                                "type": "auth_group",
                            }
                        )
                    )

                    if response:
                        response = response[0]
                        group_user_response = group_user.get_group_user(
                            build_request(
                                query_params={
                                    "group_id": response["id"],
                                    "user_id": student_data["user"]["id"],
                                }
                            )
                        )
                        if not group_user_response or group_user_response == []:
                            return False
            return True

    return False


@router.post("/")
async def create_student(request: Request):
    data = await request.body()
    query_params = validate_and_build_query_params(
        data["form_data"],
        STUDENT_QUERY_PARAMS
        + USER_QUERY_PARAMS
        + ENROLLMENT_RECORD_PARAMS
        + SCHOOL_QUERY_PARAMS
        + ["id_generation", "region", "batch_registration", "block_name"],
    )

    if not data["id_generation"]:
        student_id = query_params["student_id"]
        check_if_student_id_is_part_of_request(query_params)

        does_student_already_exist = await verify_student(
            build_request(), query_params["student_id"]
        )

        if does_student_already_exist:
            return {"student_id": query_params["student_id"], "already_exists": True}

    else:
        if data["auth_group"] == "EnableStudents":
            student_id = EnableStudents(query_params).get_student_id()
            query_params["student_id"] = student_id

            if student_id == "":
                return {
                    "student_id": query_params["student_id"],
                    "already_exists": True,
                }

        elif (
            data["auth_group"] == "FeedingIndiaStudents"
            or data["auth_group"] == "UttarakhandStudents"
            or data["auth_group"] == "HimachalStudents"
            or data["auth_group"] == "AllIndiaStudents"
            or data["auth_group"] == "ChhattisgarhStudents"
        ):
            # Use phone number as student ID
            query_params["student_id"] = query_params["phone"]
            student_id = query_params["student_id"]

            student_id_already_exists = await verify_student(
                build_request(), student_id=student_id
            )

            if student_id_already_exists:
                return {
                    "student_id": query_params["student_id"],
                    "already_exists": True,
                }
        else:
            check_if_email_or_phone_is_part_of_request(query_params)

            user_already_exists = user.get_users(
                build_request(
                    query_params={
                        "email": query_params["email"]
                        if "email" in query_params
                        else None,
                        "phone": query_params["phone"]
                        if "phone" in query_params
                        else None,
                    }
                )
            )
            if user_already_exists:
                return {
                    "student_id": query_params["student_id"],
                    "already_exists": True,
                }

    if "grade" in query_params:
        student_grade_id = grade.get_grade(
            build_request(query_params={"number": int(query_params["grade"])})
        )
        query_params["grade_id"] = student_grade_id["id"]

    if "planned_competitive_exams" in query_params:
        query_params["planned_competitive_exams"] = process_exams(
            query_params["planned_competitive_exams"]
        )

    if "physically_handicapped" in query_params:
        query_params["physically_handicapped"] = (
            "true" if query_params["physically_handicapped"] == "Yes" else "false"
        )

    new_student_data = create_new_student_record(query_params)
    await create_auth_group_user_record(new_student_data, data["auth_group"])

    if data["auth_group"] == "AllIndiaStudents":
        batch_id = f"AllIndiaStudents_{query_params['grade']}_24_A001"  # update to 26 later str(datetime.now().year)[-2:]
        await create_batch_user_record(new_student_data, batch_id)

    if (
        data["auth_group"]
        in [
            "HimachalStudents",
            "DelhiStudents",
            "UttarakhandStudents",
            "PunjabStudents",
        ]
        and "grade" in query_params
        and (
            "batch_registration" in query_params
            and query_params["batch_registration"] is True
        )
    ):
        if data["auth_group"] == "HimachalStudents":
            batch_id = f"HP-{query_params['grade']}-Selection-25"  # update 26 later
        elif data["auth_group"] == "UttarakhandStudents":
            batch_id = f"UK-{query_params['grade']}-Selection-25"  # update 26 later
        elif data["auth_group"] == "DelhiStudents":
            batch_id = f"DL-{query_params['grade']}-Selection-25"  # update 26 later
        elif data["auth_group"] == "PunjabStudents":
            batch_id = f"PB-{query_params['grade']}-Selection-25"  # update 26 later

        await create_batch_user_record(new_student_data, batch_id)

    if "grade_id" in new_student_data:
        await create_grade_user_record(new_student_data)

    if "school_name" in query_params:
        await create_school_user_record(
            new_student_data,
            query_params["school_name"],
            query_params["district"],
            data["auth_group"],
        )
    return {"student_id": query_params["student_id"], "already_exists": False}


@router.patch("/")
async def update_student(request: Request):
    data = await request.body()

    response = requests.post(student_db_url, json=data, headers=db_request_token())
    if is_response_valid(response, "Student API could not patch the data!"):
        return is_response_empty(
            response.json(), "Student API could not fetch the patched student"
        )


@router.post("/complete-profile-details")
async def complete_profile_details(request: Request):
    data = await request.json()

    student_data = build_student_and_user_data(data)

    student_response = get_students(
        build_request(query_params={"student_id": data["student_id"]})
    )

    student_data["id"] = student_response[0]["id"]
    await update_student(build_request(body=student_data))
