# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Wibias/hass-variables/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                           |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|----------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| custom\_components/variable/\_\_init\_\_.py    |      209 |        1 |       88 |        7 |     97% |180-\>182, 182-\>184, 298, 379-\>378, 547-\>549, 569-\>571, 571-\>575 |
| custom\_components/variable/binary\_sensor.py  |      208 |       46 |       80 |       19 |     75% |114-118, 153, 188, 229, 232-237, 249-252, 259-260, 271-274, 281-282, 348, 357-363, 392-398, 406-\>424, 411-418, 432, 434-\>453, 472-\>479, 481-508, 522 |
| custom\_components/variable/config\_flow.py    |      586 |       74 |      252 |       50 |     83% |410, 430-\>432, 432-\>436, 509, 515-\>517, 527, 547-555, 616, 652, 789, 864-874, 888, 891-892, 908-914, 935, 951, 983, 991-\>1004, 1036, 1038, 1042, 1068, 1100, 1108-\>1141, 1114-\>1116, 1116-\>1118, 1119, 1121, 1130-\>1132, 1155, 1212, 1246, 1318, 1352, 1454-1459, 1468-1469, 1473-\>1496, 1474-\>1476, 1481-\>1485, 1501, 1584-1595, 1604-1637, 1651, 1683, 1722, 1864, 1947, 1956, 1987, 2071, 2107-\>2109 |
| custom\_components/variable/const.py           |       39 |        0 |        0 |        0 |    100% |           |
| custom\_components/variable/device.py          |       59 |        0 |       22 |        1 |     99% | 144-\>140 |
| custom\_components/variable/device\_tracker.py |      180 |       14 |       66 |        7 |     91% |111-115, 166, 222-223, 319-325, 335-\>353, 340-347, 361, 414-\>416 |
| custom\_components/variable/helpers.py         |      181 |        1 |      104 |        2 |     99% |123-\>125, 387 |
| custom\_components/variable/sensor.py          |      274 |       42 |      100 |       14 |     83% |189, 229-230, 254-255, 281-314, 343-344, 371-\>373, 388-\>390, 438-444, 476-482, 490-\>508, 502, 530, 581-587, 600, 642, 647-655, 668 |
| **TOTAL**                                      | **1736** |  **178** |  **712** |  **100** | **87%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/Wibias/hass-variables/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/Wibias/hass-variables/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Wibias/hass-variables/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/Wibias/hass-variables/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FWibias%2Fhass-variables%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/Wibias/hass-variables/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.