package airport.entrance.management;

import java.util.List;
import java.util.Scanner;

public class AccessGate {
    public void execute(List<Person> persons, Scanner scanner) {
        int enteredID = Console.readInt(scanner, "Enter ID to access gate: ");

        for (Person person : persons) {
            if (person.getId() == enteredID) {
                System.out.println("Welcome, " + person.getName() + "!");
                return;
            }
        }

        System.out.println("Sorry, access denied.");
    }
}
