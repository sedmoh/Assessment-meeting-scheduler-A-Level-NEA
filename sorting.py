def merge_sort_meetings(meetings, key="start_time"):
    # merge sort implementation for sorting meetings
    if len(meetings) <= 1:
        return meetings

    mid = len(meetings) // 2
    left = merge_sort_meetings(meetings[:mid], key)
    right = merge_sort_meetings(meetings[mid:], key)

    return merge(left, right, key)


def merge(left, right, key):
    # merge sorted lists
    result = []
    left_index = 0
    right_index = 0

    while left_index < len(left) and right_index < len(right):
        # use getattr to access object attributes
        left_val = getattr(left[left_index], key)
        right_val = getattr(right[right_index], key)

        if left_val <= right_val:
            result.append(left[left_index])
            left_index += 1
        else:
            result.append(right[right_index])
            right_index += 1

    # add remaining elements
    result.extend(left[left_index:])
    result.extend(right[right_index:])

    return result
