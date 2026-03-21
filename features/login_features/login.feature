Feature: Login page validation

  Scenario Outline: Verify login details
    Given User is navigated to application
    When [ai] user enters <username>, <password> <Name><country> <region> <sex>
    When user clicks on login button
    Then Login should be successful
    Examples:
      | username | password | Name | country | region    | sex  |
      | Admin    | Admin123 | Venu | India   | Telangana | Male |