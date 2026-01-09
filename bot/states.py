from aiogram.fsm.state import State, StatesGroup


class AddProductStates(StatesGroup):
    """States for adding a new product."""
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_weight = State()
    waiting_for_category = State()


class NewSupplyStates(StatesGroup):
    """States for creating a new supply order."""
    waiting_for_tracking = State()
    waiting_for_date = State()
    waiting_for_products = State()
    waiting_for_quantity = State()
    waiting_for_cost_choice = State()
    waiting_for_custom_price = State()
    waiting_for_custom_weight = State()
    confirm_order = State()


class UpdateSupplyStates(StatesGroup):
    """States for updating supply order status."""
    waiting_for_tracking = State()
    waiting_for_status = State()


class DeleteSupplyStates(StatesGroup):
    """States for deleting a supply order."""
    waiting_for_identifier = State()
    waiting_for_confirm = State()


class SaleStates(StatesGroup):
    """States for registering a sale."""
    waiting_for_product = State()
    waiting_for_price_choice = State()
    waiting_for_price = State()
    waiting_for_quantity = State()
    waiting_for_seller = State()


class DeleteProductStates(StatesGroup):
    """States for deleting a product."""
    waiting_for_product = State()
    waiting_for_confirm = State()


class EditProductStates(StatesGroup):
    """States for editing a product."""
    waiting_for_product = State()
    waiting_for_field = State()
    waiting_for_value = State()


class FinanceSettingsStates(StatesGroup):
    """States for updating financial settings."""
    waiting_for_action = State()
    waiting_for_cny_rate = State()
    waiting_for_delivery_cost = State()


class ReportStates(StatesGroup):
    """States for generating reports."""
    waiting_for_period = State()
    waiting_for_seller = State()


class SettingsStates(StatesGroup):
    """States for general settings management."""
    waiting_for_seller_input = State()


class ArrivalConfirmStates(StatesGroup):
    """States for confirming auto-parsed arrival messages before updating supply statuses."""
    waiting_for_confirmation = State()
    waiting_for_manual_input = State()


class ViewSupplyItemsStates(StatesGroup):
    """States for viewing and deleting supply items by arrival date."""
    waiting_for_date = State()
    viewing_items = State()
    confirming_delete = State()
    editing_price = State()


class ViewSalesStates(StatesGroup):
    """States for viewing and deleting sales by date."""
    waiting_for_date = State()
    viewing_sales = State()
    confirming_delete = State()

