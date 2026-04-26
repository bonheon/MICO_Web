from ...common.get_data import GetData
from ...common.module import Module

family       = 'DRAM'
product_list = ['LC', 'CP']
oper_desc    = 'M1_CU_CMP'

detail_df = GetData.get_detail_info(
    family=family,
    product_list=product_list,
    oper_desc=oper_desc,
)

Module.run(detail_df)
