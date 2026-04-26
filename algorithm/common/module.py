from .get_data import GetData, MergeData
from . import pre_thk_vm as Pre_THK_VM
from . import removal_rate as Removal_Rate
from . import offset as OFFSET


class Module:

    @staticmethod
    def run(detail_df):
        group_keys = ['lot_code', 'oper_desc', 'fab']

        for (lot_code, oper_desc, fab), group_detail_df in detail_df.groupby(group_keys):
            recipe_groups = GetData.get_recipe_groups(lot_code, oper_desc, fab)

            if recipe_groups:
                for group in recipe_groups:
                    grouped_detail_df = group_detail_df[
                        group_detail_df['recipe_id'].isin(group.recipe_ids)
                    ]
                    grouped_merge_df = MergeData.get_merge_data(lot_code, oper_desc, fab)

                    # Pre_THK 학습
                    pre_thk_df = Module._run_pre_thk(grouped_merge_df, grouped_detail_df)

                    # RR 학습 — 내부에서 recipe별 저장
                    rr_df = Removal_Rate.get_group_data(grouped_merge_df, group)
                    Removal_Rate.run_group_logic(rr_df, grouped_detail_df, group)

                    # Offset 학습 — 내부에서 recipe별 저장
                    offset_df = OFFSET.get_group_data(rr_df, group)
                    OFFSET.run_group_logic(offset_df, grouped_detail_df, group)

            else:
                merge_df = MergeData.get_merge_data(lot_code, oper_desc, fab)

                for _, detail in group_detail_df.iterrows():
                    # Pre_THK 학습
                    pre_thk_df = Module._run_pre_thk(merge_df, detail)

                    # RR 학습 — 내부에서 recipe별 저장
                    rr_df = Removal_Rate.get_data(merge_df, detail)
                    Removal_Rate.run_logic(rr_df, detail)

                    # Offset 학습 — 내부에서 recipe별 저장
                    offset_df = OFFSET.get_data(rr_df, detail)
                    OFFSET.run_logic(offset_df, detail)

    @staticmethod
    def _run_pre_thk(merge_df, detail):
        detrend_df    = Pre_THK_VM.detrend(merge_df, detail)
        moving_avg_df = Pre_THK_VM.moving_avg(detrend_df, detail)
        regression_df = Pre_THK_VM.regression(moving_avg_df, detail)  # 다른 공정 회귀식
        return regression_df
