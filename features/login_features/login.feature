Feature : Login page validation

  Scenario: Verify login details
    Given User is navigated to application
    When user enters username "Admin"
    When user enter password "Admin123"
    When user clicks on login button
    Then Login should be successfull
    