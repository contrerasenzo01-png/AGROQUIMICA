
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0009_alter_alertas_id_usuario_alter_lotes_id_producto_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='movimientosstock',
                    name='ID_Usuario',
                    field=models.ForeignKey(
                        db_column='ID_Usuario',
                        on_delete=django.db.models.deletion.PROTECT,
                        to='inventario.usuarios',
                    ),
                ),
            ],
        ),
    ]
