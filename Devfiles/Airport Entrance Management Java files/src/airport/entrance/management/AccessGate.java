package airport.entrance.management;

import java.util.List;
import java.util.Scanner;

public class AccessGate {
    public void execute(List<Person> persons) {
        Scanner scanner = new Scanner(System.in);
        System.out.print("Enter ID to access gate: ");
        int enteredID = scanner.nextInt();

        for (Person person : persons) {
            if (person.getId() == enteredID) {
                System.out.println("Welcome, " + person.getName() + "!");
                return;
            }
        }

        System.out.println("Sorry, access denied.");
    }
}
