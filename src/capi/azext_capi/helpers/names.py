# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Helper function for randomly generating memorable cluster names.
"""

import random


def generate_cluster_name(seed=None):
    """
    Return a randomly-generated memorable name, such as \"earthy-mainsail.\"

    >>> generate_cluster_name(69)
    'vulcan-bagpiper'
    >>> generate_cluster_name(78)
    'gaslit-doghouse'
    >>> generate_cluster_name(929)
    'gentle-teamwork'
    """
    adjectives = [
        'ablest', 'absurd', 'actual', 'aerial', 'allied', 'artful', 'atomic', 'august',
        'bamboo', 'benign', 'blonde', 'blurry', 'bolder', 'breezy', 'bubbly', 'burley',
        'calmer', 'candid', 'casual', 'cheery', 'classy', 'clever', 'convex', 'cubist',
        'dainty', 'dapper', 'decent', 'deluxe', 'docile', 'dogged', 'drafty', 'dreamy',
        'earthy', 'easier', 'echoed', 'edible', 'elfish', 'excess', 'exotic', 'expert',
        'fabled', 'famous', 'feline', 'finest', 'flaxen', 'folksy', 'frisky', 'frozen',
        'gaslit', 'gentle', 'gifted', 'ginger', 'global', 'golden', 'grassy', 'guided',
        'haptic', 'hearty', 'hidden', 'hipper', 'honest', 'humble', 'hungry', 'hushed',
        'iambic', 'iciest', 'iconic', 'indoor', 'inward', 'ironic', 'island', 'italic',
        'jagged', 'jangly', 'jaunty', 'jicama', 'jiggly', 'jovial', 'joyful', 'junior',
        'kabuki', 'karmic', 'keener', 'kiddie', 'kindly', 'kingly', 'klutzy', 'knotty',
        'lambda', 'latest', 'leader', 'linear', 'lively', 'lonely', 'loving', 'luxury',
        'madcap', 'madras', 'marble', 'mellow', 'metric', 'modest', 'molten', 'mystic',
        'native', 'nearby', 'nested', 'newish', 'nickel', 'nimbus', 'nonfat', 'normal',
        'oblong', 'oddest', 'offset', 'oldest', 'onside', 'orange', 'outlaw', 'owlish',
        'padded', 'pastry', 'peachy', 'pepper', 'player', 'preset', 'proper', 'pulsar',
        'quacky', 'quaint', 'quartz', 'queens', 'queued', 'quinoa', 'quirky', 'quoted',
        'racing', 'rental', 'ribbed', 'rising', 'rococo', 'rubber', 'rugged', 'rustic',
        'sanest', 'scenic', 'seeing', 'shadow', 'skiing', 'stable', 'steely', 'syrupy',
        'taller', 'tender', 'tested', 'timely', 'trendy', 'triple', 'truthy', 'twenty',
        'ultima', 'unbent', 'unisex', 'united', 'upbeat', 'uphill', 'usable', 'utmost',
        'vacuum', 'valued', 'vanity', 'velcro', 'velvet', 'verbal', 'violet', 'vulcan',
        'walkup', 'webbed', 'wicker', 'wiggly', 'wilder', 'wonder', 'wooden', 'woodsy',
        'yearly', 'yeasty', 'yellow', 'yeoman', 'yogurt', 'yonder', 'youthy', 'yuppie',
        'zaftig', 'zanier', 'zephyr', 'zeroed', 'zigzag', 'zipped', 'zircon', 'zydeco',
    ]
    nouns = [
        'addendum', 'anaconda', 'airfield', 'aqualung', 'armchair', 'asteroid', 'autoharp',
        'babushka', 'backbone', 'bagpiper', 'barbecue', 'bookworm', 'bullfrog', 'buttress',
        'caffeine', 'checkers', 'chinbone', 'countess', 'crawfish', 'cucumber', 'cutpurse',
        'daffodil', 'darkroom', 'deadbolt', 'doghouse', 'dragster', 'drumroll', 'duckling',
        'earrings', 'earthman', 'eggplant', 'electron', 'elephant', 'espresso', 'eyetooth',
        'falconer', 'farmland', 'ferryman', 'fireball', 'fishbone', 'footwear', 'frosting',
        'gadabout', 'gasworks', 'gatepost', 'gemstone', 'gladness', 'goldfish', 'greenery',
        'hacienda', 'handbill', 'hardtack', 'hawthorn', 'headwind', 'henhouse', 'huntress',
        'icehouse', 'idealist', 'inchworm', 'instinct', 'inventor', 'insignia', 'ironwood',
        'jailbird', 'jamboree', 'jerrycan', 'jetliner', 'jokester', 'joyrider', 'jumpsuit',
        'kangaroo', 'keepsake', 'kerchief', 'keypunch', 'kingfish', 'knapsack', 'knothole',
        'ladybird', 'lakeside', 'lambskin', 'landmass', 'larkspur', 'lollipop', 'lungfish',
        'macaroni', 'mackinaw', 'magician', 'mainsail', 'milepost', 'mongoose', 'moonrise',
        'nailhead', 'nautilus', 'neckwear', 'newsreel', 'nonesuch', 'novelist', 'nuthatch',
        'occupant', 'odometer', 'offering', 'offshoot', 'original', 'organism', 'overalls',
        'pachinko', 'painting', 'pamphlet', 'paneling', 'pendulum', 'playroom', 'ponytail',
        'quacking', 'quadrant', 'quantity', 'queendom', 'question', 'quilting', 'quotient',
        'rabbitry', 'radiator', 'renegade', 'ricochet', 'riverbed', 'rosewood', 'rucksack',
        'sailfish', 'sandwich', 'sculptor', 'seashore', 'seedcake', 'skylight', 'stickpin',
        'tabletop', 'tailbone', 'teamwork', 'teaspoon', 'tinkerer', 'traverse', 'turbojet',
        'umbrella', 'underdog', 'undertow', 'unicycle', 'universe', 'uptowner', 'utensils',
        'vacation', 'vagabond', 'valkyrie', 'variable', 'villager', 'vineyard', 'vocalist',
        'waggoner', 'waxworks', 'waterbed', 'wayfarer', 'whitecap', 'windmill', 'woodshed',
        'yachting', 'yardbird', 'yardwork', 'yearbook', 'yearling', 'yeomanry', 'yodeling',
        'zaniness', 'zeppelin', 'ziggurat', 'zillions', 'zirconia', 'zoologer', 'zucchini',
    ]
    random.seed(seed)
    return f"{random.choice(adjectives)}-{random.choice(nouns)}"


if __name__ == "__main__":
    import doctest
    doctest.testmod()

    print(generate_cluster_name())
