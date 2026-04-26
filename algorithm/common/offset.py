def get_data(rr_df, detail):
    # rr 결과 기반 offset 데이터 준비 (recipe_id 기준 필터링)
    recipe_id = detail['recipe_id']
    return rr_df[rr_df['Recipe_ID'] == recipe_id]


def run_logic(offset_df, detail):
    # offset 학습 후 recipe별 저장
    result = _learn(offset_df, detail)
    _save_result(result, detail['recipe_id'])


def get_group_data(rr_df, group):
    # 그룹 내 모든 recipe_id의 rr data 합산
    return rr_df[rr_df['Recipe_ID'].isin(group.recipe_ids)]


def run_group_logic(offset_df, group_detail_df, group):
    # 그룹 합산 데이터로 한 번 학습
    result = _learn(offset_df, group_detail_df)
    # 동일한 결과를 그룹 내 recipe_id별로 저장
    for recipe_id in group.recipe_ids:
        _save_result(result, recipe_id)


def _learn(offset_df, detail_or_df):
    # TODO: 실제 학습 로직
    pass


def _save_result(result, recipe_id):
    # TODO: DB 저장 로직
    pass
