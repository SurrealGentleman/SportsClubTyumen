from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqladmin import ModelView, action
from sqladmin.fields import SelectField
from wtforms import Form

from app.core.time import APP_TIMEZONE, local_datetime
from app.models import (
    Competition,
    Registration,
    RegistrationMember,
    RegistrationType,
    Sport,
    Training,
)
from app.models.training import WEEKDAY_CHOICES, WEEKDAY_NAMES
from app.services.excel_export import build_competition_registrations_xlsx


def format_admin_datetime(model: object, attribute: str) -> str:
    value = getattr(model, attribute)
    if value is None:
        return "Не зафиксировано"
    return local_datetime(value).strftime("%d.%m.%Y %H:%M")


def format_weekday(model: Training, _attribute: str) -> str:
    return WEEKDAY_NAMES[model.weekday]


def format_registration_type(model: Competition, _attribute: str) -> str:
    return str(model.registration_type)


class RussianAdminForm(Form):
    class Meta:
        locales = ["ru"]


class CompetitionAdminForm(RussianAdminForm):
    def validate(self, extra_validators: dict | None = None) -> bool:
        minimum = self["min_team_size"]
        maximum = self["max_team_size"]
        if self["registration_type"].data == RegistrationType.individual.value:
            for field in (minimum, maximum):
                field.data = None
                field.raw_data = []
                field.process_errors = []
            return super().validate(extra_validators)

        valid = super().validate(extra_validators)
        if self["registration_type"].data != RegistrationType.team.value:
            return valid
        for field, label in ((minimum, "минимум"), (maximum, "максимум")):
            if field.data is None:
                if not field.errors:
                    field.errors.append(
                        f"Для командного соревнования укажите {label} участников"
                    )
                valid = False
            elif field.data < 1:
                field.errors.append("Количество участников должно быть не меньше 1")
                valid = False
        if minimum.data is not None and maximum.data is not None:
            if maximum.data < minimum.data:
                maximum.errors.append(
                    "Максимум участников не может быть меньше минимума"
                )
                valid = False
        return valid


class RussianModelView(ModelView):
    form_base_class = RussianAdminForm

    @staticmethod
    def database_error_message(exc: SQLAlchemyError) -> str:
        if isinstance(exc, IntegrityError):
            constraint = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            messages = {
                "ck_competitions_team_size": (
                    "Для командного соревнования укажите минимум и максимум участников. "
                    "Оба значения должны быть не меньше 1, а максимум — не меньше минимума."
                ),
                "ck_competitions_date_range": (
                    "Дата окончания соревнования не может быть раньше даты начала."
                ),
            }
            for name, message in messages.items():
                if constraint == name or f"CHECK constraint failed: {name}" in str(
                    exc.orig
                ):
                    return message
            return "Не удалось сохранить запись: данные нарушают ограничения. Проверьте значения и наличие повторяющихся записей."
        return "Не удалось сохранить запись. Повторите попытку позже."

    async def insert_model(self, request: Request, data: dict):
        try:
            return await super().insert_model(request, data)
        except SQLAlchemyError as exc:
            raise ValueError(self.database_error_message(exc)) from None

    async def update_model(self, request: Request, pk: str, data: dict):
        try:
            return await super().update_model(request, pk, data)
        except SQLAlchemyError as exc:
            raise ValueError(self.database_error_message(exc)) from None


class SportAdmin(RussianModelView, model=Sport):
    name = "Вид спорта"
    name_plural = "Виды спорта"
    icon = "fa-solid fa-person-running"

    column_list = [Sport.id, Sport.name, Sport.slug, Sport.is_active, Sport.updated_at]
    column_searchable_list = [Sport.name, Sport.slug]
    column_sortable_list = [Sport.id, Sport.name, Sport.slug, Sport.is_active]
    column_default_sort = [(Sport.name, False)]
    form_excluded_columns = [
        Sport.slug,
        Sport.image_path,
        Sport.created_at,
        Sport.updated_at,
        Sport.trainings,
    ]
    column_formatters = {Sport.updated_at: format_admin_datetime}
    column_labels = {
        Sport.id: "ID",
        Sport.name: "Название",
        Sport.slug: "Адрес страницы",
        Sport.description: "Описание",
        Sport.is_active: "Активен",
        Sport.updated_at: "Обновлён",
    }


class TrainingAdmin(RussianModelView, model=Training):
    name = "Тренировка"
    name_plural = "Тренировки"
    icon = "fa-solid fa-calendar-days"

    column_list = [
        Training.id,
        Training.sport,
        Training.group_name,
        Training.weekday,
        Training.start_time,
        Training.end_time,
        Training.is_active,
    ]
    column_searchable_list = [
        Training.group_name,
        Training.location,
        Training.coach_name,
    ]
    column_sortable_list = [Training.id, Training.weekday, Training.start_time]
    column_default_sort = [(Training.weekday, False), (Training.start_time, False)]
    form_overrides = {Training.weekday: SelectField}
    form_args = {
        "weekday": {
            "choices": WEEKDAY_CHOICES,
            "coerce": int,
        }
    }
    column_formatters = {
        Training.group_name: lambda model, _attribute: str(model.group_name),
        Training.weekday: format_weekday,
    }
    column_formatters_detail = column_formatters
    column_labels = {
        Training.id: "ID",
        Training.sport: "Вид спорта",
        Training.group_name: "Группа",
        Training.weekday: "День недели",
        Training.start_time: "Начало",
        Training.end_time: "Окончание",
        Training.location: "Место",
        Training.coach_name: "Тренер",
        Training.coach_email: "Почта тренера",
        Training.notes: "Примечания",
        Training.is_active: "Активна",
    }


class CompetitionAdmin(RussianModelView, model=Competition):
    name = "Соревнование"
    name_plural = "Соревнования"
    icon = "fa-solid fa-trophy"
    can_view_details = True
    form_base_class = CompetitionAdminForm
    create_template = "sqladmin/competition_create.html"
    edit_template = "sqladmin/competition_edit.html"

    column_list = [
        Competition.id,
        Competition.title,
        Competition.start_date,
        Competition.registration_type,
        Competition.registration_deadline,
        Competition.is_registration_open,
        Competition.is_published,
    ]
    column_searchable_list = [Competition.title, Competition.slug, Competition.location]
    column_sortable_list = [
        Competition.id,
        Competition.title,
        Competition.start_date,
        Competition.registration_deadline,
    ]
    column_default_sort = [(Competition.start_date, True)]
    form_excluded_columns = [
        Competition.slug,
        Competition.created_at,
        Competition.updated_at,
        Competition.registrations,
    ]
    form_overrides = {Competition.registration_type: SelectField}
    form_args = {
        "registration_type": {
            "choices": [
                (RegistrationType.individual.value, "Индивидуальная"),
                (RegistrationType.team.value, "Командная"),
            ],
            "coerce": str,
        },
        "registration_deadline": {
            "display_timezone": APP_TIMEZONE,
            "description": "Дата и время Тюмени (UTC+5)",
        },
        "min_team_size": {
            "description": "Обязательно для командного формата. Капитан входит в число участников.",
        },
        "max_team_size": {
            "description": "Обязательно для командного формата. Не меньше указанного минимума.",
        },
    }
    column_formatters = {
        Competition.registration_type: format_registration_type,
        Competition.registration_deadline: format_admin_datetime,
    }
    column_formatters_detail = column_formatters
    column_labels = {
        Competition.id: "ID",
        Competition.title: "Название",
        Competition.slug: "Адрес страницы",
        Competition.description: "Описание",
        Competition.location: "Место",
        Competition.start_date: "Дата начала",
        Competition.end_date: "Дата окончания",
        Competition.registration_deadline: "Дедлайн регистрации",
        Competition.registration_type: "Тип регистрации",
        Competition.min_team_size: "Минимум участников",
        Competition.max_team_size: "Максимум участников",
        Competition.is_registration_open: "Регистрация открыта",
        Competition.is_published: "Опубликовано",
    }

    async def on_model_change(
        self, data: dict, model: Competition, is_created: bool, request: Request
    ) -> None:
        if data.get("registration_type") == RegistrationType.individual.value:
            data["min_team_size"] = None
            data["max_team_size"] = None
        elif data.get("registration_type") == RegistrationType.team.value:
            minimum = data.get("min_team_size")
            maximum = data.get("max_team_size")
            if minimum is None or maximum is None:
                raise ValueError(
                    "Для командного соревнования укажите минимум и максимум участников"
                )
            if minimum < 1 or maximum < 1:
                raise ValueError("Количество участников должно быть не меньше 1")
            if maximum < minimum:
                raise ValueError("Максимум участников не может быть меньше минимума")

    @action(
        name="export-xlsx",
        label="Выгрузить заявки в Excel",
        add_in_detail=True,
        add_in_list=True,
    )
    async def export_xlsx(self, request: Request) -> Response:
        raw_ids = request.query_params.get("pks", "")
        competition_ids = [value for value in raw_ids.split(",") if value]
        if len(competition_ids) != 1 or not competition_ids[0].isdigit():
            return Response(
                "Выберите одно соревнование для выгрузки.",
                status_code=400,
            )

        statement = (
            select(Competition)
            .options(
                selectinload(Competition.registrations).selectinload(
                    Registration.members
                )
            )
            .where(Competition.id == int(competition_ids[0]))
        )
        with self.session_maker() as session:
            competition = session.scalar(statement)
            if competition is None:
                return Response("Соревнование не найдено.", status_code=404)
            output = build_competition_registrations_xlsx(competition)

        filename = f"{competition.slug}-registrations.xlsx"
        return Response(
            content=output.getvalue(),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


class RegistrationAdmin(RussianModelView, model=Registration):
    name = "Заявка"
    name_plural = "Заявки"
    icon = "fa-solid fa-clipboard-list"

    can_view_details = True
    column_list = [
        Registration.id,
        Registration.competition,
        Registration.team_name,
        Registration.captain_name,
        Registration.captain_email,
        Registration.created_at,
    ]
    column_details_list = [
        Registration.id,
        Registration.competition,
        Registration.team_name,
        Registration.captain_name,
        Registration.captain_email,
        Registration.captain_phone,
        Registration.members,
        Registration.created_at,
        Registration.personal_data_consent_at,
        Registration.consent_document_version,
        Registration.members_consents_confirmed_at,
    ]
    column_searchable_list = [
        Registration.team_name,
        Registration.captain_name,
        Registration.captain_email,
    ]
    column_sortable_list = [Registration.id, Registration.created_at]
    column_default_sort = [(Registration.created_at, True)]
    form_excluded_columns = [
        Registration.created_at,
        Registration.members,
        Registration.personal_data_consent_at,
        Registration.consent_document_version,
        Registration.consent_document_text,
        Registration.members_consents_confirmed_at,
    ]
    column_formatters = {
        Registration.created_at: format_admin_datetime,
        Registration.personal_data_consent_at: format_admin_datetime,
        Registration.members_consents_confirmed_at: format_admin_datetime,
    }
    column_formatters_detail = column_formatters
    column_labels = {
        Registration.id: "ID",
        Registration.competition: "Соревнование",
        Registration.team_name: "Команда",
        Registration.captain_name: "Капитан / участник",
        Registration.captain_email: "Почта",
        Registration.captain_phone: "Телефон",
        Registration.members: "Участники",
        Registration.created_at: "Создана",
        Registration.personal_data_consent_at: "Согласие участника / капитана",
        Registration.consent_document_version: "Версия документа согласия",
        Registration.members_consents_confirmed_at: "Подтверждение капитана о согласиях участников",
    }


class RegistrationMemberAdmin(RussianModelView, model=RegistrationMember):
    name = "Участник заявки"
    name_plural = "Участники заявок"
    icon = "fa-solid fa-users"

    can_view_details = True
    column_list = [
        RegistrationMember.id,
        RegistrationMember.registration,
        RegistrationMember.full_name,
        RegistrationMember.university_email,
        RegistrationMember.institute,
        RegistrationMember.course,
        RegistrationMember.is_captain,
    ]
    column_searchable_list = [
        RegistrationMember.full_name,
        RegistrationMember.university_email,
        RegistrationMember.institute,
        RegistrationMember.group_name,
    ]
    column_sortable_list = [
        RegistrationMember.id,
        RegistrationMember.full_name,
        RegistrationMember.course,
    ]
    column_labels = {
        RegistrationMember.id: "ID",
        RegistrationMember.registration: "Заявка",
        RegistrationMember.full_name: "ФИО",
        RegistrationMember.university_email: "Почта ТюмГУ",
        RegistrationMember.institute: "Институт",
        RegistrationMember.course: "Курс",
        RegistrationMember.group_name: "Группа",
        RegistrationMember.phone: "Телефон",
        RegistrationMember.is_captain: "Капитан",
    }


ADMIN_VIEWS = (
    SportAdmin,
    TrainingAdmin,
    CompetitionAdmin,
    RegistrationAdmin,
    RegistrationMemberAdmin,
)
