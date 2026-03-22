from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from .models import Account


class AccountResource(resources.ModelResource):
    parent = fields.Field(
        column_name="parent",
        attribute="parent",
        widget=ForeignKeyWidget(Account, "code"),
    )

    class Meta:
        model = Account
        fields = (
            "id",
            "code",
            "name",
            "account_type",
            "parent",
            "is_active",
            "is_postable",
        )
        import_id_fields = ("code",)
