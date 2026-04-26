def get_data(merge_df, detail):
    # recipe 버그 수정: 현재 진행 중인 recipe_id만 필터링
    recipe_id = detail['recipe_id']
    return merge_df[merge_df['Recipe_ID'] == recipe_id]


def run_logic(rr_df, detail):
    # eq / recipe 기준 학습 후 recipe별 저장
    result = _learn(rr_df, detail)
    _save_result(result, detail['recipe_id'])


def get_group_data(merge_df, group):
    # 그룹 내 모든 recipe_id의 merge data 합산
    return merge_df[merge_df['Recipe_ID'].isin(group.recipe_ids)]


def run_group_logic(rr_df, group_detail_df, group):
    # 그룹 합산 데이터로 한 번 학습
    result = _learn(rr_df, group_detail_df)
    # 동일한 결과를 그룹 내 recipe_id별로 저장
    for recipe_id in group.recipe_ids:
        _save_result(result, recipe_id)


def _learn(rr_df, detail_or_df):
    # TODO: 실제 학습 로직
    pass


def _save_result(result, recipe_id):
    # TODO: DB 저장 로직
    pass
